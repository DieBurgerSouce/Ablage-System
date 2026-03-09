# -*- coding: utf-8 -*-
"""
Unit Tests fuer Dokumenten-Clustering API Endpoints.

Testet:
- POST /documents/{id}/cluster-suggestions (Vorschlaege generieren)
- GET  /documents/{id}/cluster-suggestions (Offene Vorschlaege)
- POST /cluster-suggestions/{id}/accept
- POST /cluster-suggestions/{id}/reject
- GET  /clusters (Cluster auflisten)
- POST /clusters (Manuellen Cluster erstellen)
- GET  /clusters/{id} (Cluster-Detail)
- GET  /clusters/{id}/graph (Graph-Daten)
- POST /clusters/auto-generate (Automatisches Clustering)
- POST /clusters/merge (Cluster zusammenfuehren)
- GET  /clusters/stats (Cluster-Statistiken)
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from starlette.requests import Request
from starlette.datastructures import Headers

pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================


def _make_request(path: str = "/api/v1/clusters", method: str = "GET") -> Request:
    """Erstellt ein echtes Starlette Request-Objekt fuer Rate-Limiter-Kompatibilitaet."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": Headers({}).raw,
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    request.state.view_rate_limit = None
    request.state._rate_limiting_complete = True
    return request


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Bypass Rate-Limiter fuer alle Tests."""
    with patch(
        "app.core.rate_limiting.limiter._check_request_limit",
        new_callable=AsyncMock,
    ) as mock_check:
        mock_check.return_value = None
        yield mock_check


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Mock authentifizierter Benutzer."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@ablage.local"
    user.is_active = True
    return user


@pytest.fixture
def company_id():
    """Test Company-ID."""
    return uuid4()


@pytest.fixture
def mock_suggestion():
    """Mock ClusterSuggestion-Objekt."""
    suggestion = MagicMock()
    suggestion.id = uuid4()
    suggestion.document_id = uuid4()
    suggestion.suggested_cluster_id = uuid4()
    suggestion.suggested_entity_id = None
    suggestion.suggested_category = "rechnung"
    suggestion.similarity_score = 0.85
    suggestion.reference_document_id = uuid4()
    suggestion.status = "pending"
    suggestion.responded_at = None
    suggestion.created_at = datetime.now(timezone.utc)
    return suggestion


@pytest.fixture
def mock_cluster():
    """Mock Cluster-Objekt."""
    cluster = MagicMock()
    cluster.id = uuid4()
    cluster.name = "Rechnungen Q1 2026"
    cluster.description = "Cluster fuer Q1 Rechnungen"
    cluster.cluster_type = "manual"
    cluster.document_count = 15
    cluster.avg_similarity = 0.78
    cluster.company_id = uuid4()
    cluster.business_entity_id = None
    cluster.parent_cluster_id = None
    cluster.is_active = True
    cluster.created_at = datetime.now(timezone.utc)
    cluster.updated_at = datetime.now(timezone.utc)
    return cluster


# =============================================================================
# Cluster-Suggestion Tests
# =============================================================================


class TestGenerateClusterSuggestions:
    """Tests fuer POST /documents/{id}/cluster-suggestions."""

    @pytest.mark.asyncio
    async def test_generate_suggestions_success(self, mock_db, mock_user, mock_suggestion, company_id):
        """Vorschlaege werden erfolgreich generiert."""
        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.suggest_for_document = AsyncMock(
                return_value=[mock_suggestion]
            )

            from app.api.v1.clustering import generate_cluster_suggestions

            doc_id = uuid4()
            result = await generate_cluster_suggestions(
                request=_make_request("/api/v1/documents/x/cluster-suggestions", "POST"),
                document_id=doc_id,
                top_k=3,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.document_id == doc_id
            assert result.total == 1
            assert len(result.suggestions) == 1
            mock_service.suggest_for_document.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_suggestions_no_company(self, mock_db, mock_user):
        """Fehler wenn kein Company-Kontext vorhanden."""
        from fastapi import HTTPException
        from app.api.v1.clustering import generate_cluster_suggestions

        with pytest.raises(HTTPException) as exc_info:
            await generate_cluster_suggestions(
                request=_make_request("/api/v1/documents/x/cluster-suggestions", "POST"),
                document_id=uuid4(),
                top_k=3,
                db=mock_db,
                current_user=mock_user,
                company_id=None,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generate_suggestions_no_embedding(self, mock_db, mock_user, company_id):
        """422 wenn Dokument kein Embedding hat."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.suggest_for_document = AsyncMock(
                side_effect=ValueError("Dokument hat kein Embedding")
            )

            from app.api.v1.clustering import generate_cluster_suggestions

            with pytest.raises(HTTPException) as exc_info:
                await generate_cluster_suggestions(
                    request=_make_request("/api/v1/documents/x/cluster-suggestions", "POST"),
                    document_id=uuid4(),
                    top_k=3,
                    db=mock_db,
                    current_user=mock_user,
                    company_id=company_id,
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_suggestions_not_found(self, mock_db, mock_user, company_id):
        """404 wenn Dokument nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.suggest_for_document = AsyncMock(
                side_effect=ValueError("Dokument nicht gefunden")
            )

            from app.api.v1.clustering import generate_cluster_suggestions

            with pytest.raises(HTTPException) as exc_info:
                await generate_cluster_suggestions(
                    request=_make_request("/api/v1/documents/x/cluster-suggestions", "POST"),
                    document_id=uuid4(),
                    top_k=3,
                    db=mock_db,
                    current_user=mock_user,
                    company_id=company_id,
                )
            assert exc_info.value.status_code == 404


class TestGetDocumentSuggestions:
    """Tests fuer GET /documents/{id}/cluster-suggestions."""

    @pytest.mark.asyncio
    async def test_get_pending_suggestions_success(self, mock_db, mock_user, mock_suggestion, company_id):
        """Offene Vorschlaege werden korrekt zurueckgegeben."""
        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.get_pending_suggestions = AsyncMock(
                return_value=[mock_suggestion]
            )

            from app.api.v1.clustering import get_document_suggestions

            doc_id = uuid4()
            result = await get_document_suggestions(
                request=_make_request("/api/v1/documents/x/cluster-suggestions"),
                document_id=doc_id,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.document_id == doc_id
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_pending_suggestions_no_company(self, mock_db, mock_user):
        """Fehler ohne Company-Kontext."""
        from fastapi import HTTPException
        from app.api.v1.clustering import get_document_suggestions

        with pytest.raises(HTTPException) as exc_info:
            await get_document_suggestions(
                request=_make_request("/api/v1/documents/x/cluster-suggestions"),
                document_id=uuid4(),
                db=mock_db,
                current_user=mock_user,
                company_id=None,
            )
        assert exc_info.value.status_code == 400


class TestAcceptRejectSuggestion:
    """Tests fuer POST /cluster-suggestions/{id}/accept und /reject."""

    @pytest.mark.asyncio
    async def test_accept_suggestion_success(self, mock_db, mock_user, mock_suggestion):
        """Vorschlag wird erfolgreich akzeptiert."""
        mock_suggestion.status = "accepted"

        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.accept_suggestion = AsyncMock(return_value=mock_suggestion)

            from app.api.v1.clustering import accept_suggestion

            result = await accept_suggestion(
                request=_make_request("/api/v1/cluster-suggestions/x/accept", "POST"),
                suggestion_id=mock_suggestion.id,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.status == "accepted"
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_accept_suggestion_not_found(self, mock_db, mock_user):
        """404 wenn Vorschlag nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.accept_suggestion = AsyncMock(
                side_effect=ValueError("Vorschlag nicht gefunden")
            )

            from app.api.v1.clustering import accept_suggestion

            with pytest.raises(HTTPException) as exc_info:
                await accept_suggestion(
                    request=_make_request("/api/v1/cluster-suggestions/x/accept", "POST"),
                    suggestion_id=uuid4(),
                    db=mock_db,
                    current_user=mock_user,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_suggestion_success(self, mock_db, mock_user, mock_suggestion):
        """Vorschlag wird erfolgreich abgelehnt."""
        mock_suggestion.status = "rejected"

        with patch(
            "app.api.v1.clustering.ClusterSuggestionService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.reject_suggestion = AsyncMock(return_value=mock_suggestion)

            from app.api.v1.clustering import reject_suggestion

            result = await reject_suggestion(
                request=_make_request("/api/v1/cluster-suggestions/x/reject", "POST"),
                suggestion_id=mock_suggestion.id,
                db=mock_db,
                current_user=mock_user,
            )

            assert result.status == "rejected"
            mock_db.commit.assert_awaited_once()


# =============================================================================
# Cluster Management Tests
# =============================================================================


class TestListClusters:
    """Tests fuer GET /clusters."""

    @pytest.mark.asyncio
    async def test_list_clusters_success(self, mock_db, mock_user, mock_cluster, company_id):
        """Cluster werden paginiert zurueckgegeben."""
        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.list_clusters = AsyncMock(return_value=[mock_cluster])
            mock_service.count_clusters = AsyncMock(return_value=1)

            from app.api.v1.clustering import list_clusters

            result = await list_clusters(
                request=_make_request("/api/v1/clusters"),
                cluster_type=None,
                is_active=True,
                limit=50,
                offset=0,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.total == 1
            assert len(result.clusters) == 1
            assert result.limit == 50
            assert result.offset == 0

    @pytest.mark.asyncio
    async def test_list_clusters_no_company(self, mock_db, mock_user):
        """Fehler ohne Company-Kontext."""
        from fastapi import HTTPException
        from app.api.v1.clustering import list_clusters

        with pytest.raises(HTTPException) as exc_info:
            await list_clusters(
                request=_make_request("/api/v1/clusters"),
                cluster_type=None,
                is_active=True,
                limit=50,
                offset=0,
                db=mock_db,
                current_user=mock_user,
                company_id=None,
            )
        assert exc_info.value.status_code == 400


class TestCreateCluster:
    """Tests fuer POST /clusters."""

    @pytest.mark.asyncio
    async def test_create_cluster_success(self, mock_db, mock_user, mock_cluster, company_id):
        """Manueller Cluster wird erfolgreich erstellt."""
        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.create_cluster = AsyncMock(return_value=mock_cluster)

            from app.api.v1.clustering import create_cluster, ClusterCreateRequest

            body = ClusterCreateRequest(
                name="Test Cluster",
                description="Beschreibung",
                cluster_type="manual",
            )

            result = await create_cluster(
                request=_make_request("/api/v1/clusters", "POST"),
                body=body,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.name == "Rechnungen Q1 2026"
            mock_db.commit.assert_awaited_once()


class TestGetClusterDetail:
    """Tests fuer GET /clusters/{id}."""

    @pytest.mark.asyncio
    async def test_get_cluster_detail_success(self, mock_db, mock_user, mock_cluster, company_id):
        """Cluster-Detail wird korrekt zurueckgegeben."""
        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.get_cluster = AsyncMock(return_value=mock_cluster)

            from app.api.v1.clustering import get_cluster_detail

            result = await get_cluster_detail(
                request=_make_request("/api/v1/clusters/x"),
                cluster_id=mock_cluster.id,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.name == "Rechnungen Q1 2026"
            assert result.is_active is True

    @pytest.mark.asyncio
    async def test_get_cluster_detail_not_found(self, mock_db, mock_user, company_id):
        """404 wenn Cluster nicht gefunden."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.get_cluster = AsyncMock(return_value=None)

            from app.api.v1.clustering import get_cluster_detail

            with pytest.raises(HTTPException) as exc_info:
                await get_cluster_detail(
                    request=_make_request("/api/v1/clusters/x"),
                    cluster_id=uuid4(),
                    db=mock_db,
                    current_user=mock_user,
                    company_id=company_id,
                )
            assert exc_info.value.status_code == 404


class TestClusterGraph:
    """Tests fuer GET /clusters/{id}/graph."""

    @pytest.mark.asyncio
    async def test_get_cluster_graph_success(self, mock_db, mock_user, company_id):
        """Graph-Daten werden korrekt zurueckgegeben."""
        graph_data = {
            "nodes": [
                {"id": "n1", "label": "Rechnung A", "type": "document", "size": 1, "metadata": {}},
                {"id": "n2", "label": "Cluster X", "type": "cluster", "size": 5, "metadata": {}},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "weight": 0.9, "label": "member_of"},
            ],
        }

        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.get_cluster_graph_data = AsyncMock(return_value=graph_data)

            from app.api.v1.clustering import get_cluster_graph

            result = await get_cluster_graph(
                request=_make_request("/api/v1/clusters/x/graph"),
                cluster_id=uuid4(),
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert len(result.nodes) == 2
            assert len(result.edges) == 1
            assert result.edges[0].weight == 0.9

    @pytest.mark.asyncio
    async def test_get_cluster_graph_not_found(self, mock_db, mock_user, company_id):
        """404 wenn Cluster nicht existiert."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.get_cluster_graph_data = AsyncMock(
                side_effect=ValueError("Cluster nicht gefunden")
            )

            from app.api.v1.clustering import get_cluster_graph

            with pytest.raises(HTTPException) as exc_info:
                await get_cluster_graph(
                    request=_make_request("/api/v1/clusters/x/graph"),
                    cluster_id=uuid4(),
                    db=mock_db,
                    current_user=mock_user,
                    company_id=company_id,
                )
            assert exc_info.value.status_code == 404


class TestAutoGenerateClusters:
    """Tests fuer POST /clusters/auto-generate."""

    @pytest.mark.asyncio
    async def test_auto_generate_success(self, mock_db, mock_user, mock_cluster, company_id):
        """Automatisches Clustering erstellt neue Cluster."""
        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.auto_cluster_documents = AsyncMock(
                return_value=[mock_cluster]
            )

            from app.api.v1.clustering import auto_generate_clusters, AutoClusterRequest

            body = AutoClusterRequest(
                min_cluster_size=3,
                similarity_threshold=0.7,
            )

            result = await auto_generate_clusters(
                request=_make_request("/api/v1/clusters/auto-generate", "POST"),
                body=body,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.clusters_created == 1
            assert "1 Cluster" in result.message


class TestMergeClusters:
    """Tests fuer POST /clusters/merge."""

    @pytest.mark.asyncio
    async def test_merge_clusters_success(self, mock_db, mock_user, mock_cluster, company_id):
        """Cluster werden erfolgreich zusammengefuehrt."""
        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.merge_clusters = AsyncMock(return_value=mock_cluster)

            from app.api.v1.clustering import merge_clusters, MergeClustersRequest

            body = MergeClustersRequest(cluster_ids=[uuid4(), uuid4()])

            result = await merge_clusters(
                request=_make_request("/api/v1/clusters/merge", "POST"),
                body=body,
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert result.name == "Rechnungen Q1 2026"

    @pytest.mark.asyncio
    async def test_merge_clusters_value_error(self, mock_db, mock_user, company_id):
        """400 bei ungueltigem Merge-Request."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.merge_clusters = AsyncMock(
                side_effect=ValueError("Cluster gehoeren nicht zur gleichen Company")
            )

            from app.api.v1.clustering import merge_clusters, MergeClustersRequest

            body = MergeClustersRequest(cluster_ids=[uuid4(), uuid4()])

            with pytest.raises(HTTPException) as exc_info:
                await merge_clusters(
                    request=_make_request("/api/v1/clusters/merge", "POST"),
                    body=body,
                    db=mock_db,
                    current_user=mock_user,
                    company_id=company_id,
                )
            assert exc_info.value.status_code == 400


class TestClusterStats:
    """Tests fuer GET /clusters/stats."""

    @pytest.mark.asyncio
    async def test_get_cluster_stats_success(self, mock_db, mock_user, company_id):
        """Cluster-Statistiken werden korrekt zurueckgegeben."""
        stats_data = [
            {
                "cluster_id": str(uuid4()),
                "name": "Auto-Cluster",
                "cluster_type": "auto",
                "document_count": 12,
                "avg_similarity": 0.82,
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "actual_member_count": 12,
            }
        ]

        with patch(
            "app.api.v1.clustering.ClusterManagementService"
        ) as MockService:
            mock_service = MockService.return_value
            mock_service.get_cluster_stats = AsyncMock(return_value=stats_data)

            from app.api.v1.clustering import get_cluster_stats

            result = await get_cluster_stats(
                request=_make_request("/api/v1/clusters/stats"),
                db=mock_db,
                current_user=mock_user,
                company_id=company_id,
            )

            assert len(result) == 1
            assert result[0].document_count == 12
            assert result[0].avg_similarity == 0.82


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestClusteringSchemas:
    """Tests fuer Pydantic-Schema-Validierung."""

    def test_cluster_create_request_valid(self):
        """Gueltiger ClusterCreateRequest."""
        from app.api.v1.clustering import ClusterCreateRequest

        req = ClusterCreateRequest(name="Test Cluster")
        assert req.name == "Test Cluster"
        assert req.cluster_type == "manual"

    def test_cluster_create_request_empty_name(self):
        """Leerer Name wird abgelehnt."""
        from pydantic import ValidationError
        from app.api.v1.clustering import ClusterCreateRequest

        with pytest.raises(ValidationError):
            ClusterCreateRequest(name="")

    def test_auto_cluster_request_bounds(self):
        """AutoClusterRequest validiert Grenzwerte."""
        from pydantic import ValidationError
        from app.api.v1.clustering import AutoClusterRequest

        req = AutoClusterRequest(min_cluster_size=5, similarity_threshold=0.8)
        assert req.min_cluster_size == 5

        with pytest.raises(ValidationError):
            AutoClusterRequest(min_cluster_size=1)

        with pytest.raises(ValidationError):
            AutoClusterRequest(similarity_threshold=0.1)

    def test_merge_request_needs_at_least_two(self):
        """MergeClustersRequest braucht mindestens 2 IDs."""
        from pydantic import ValidationError
        from app.api.v1.clustering import MergeClustersRequest

        with pytest.raises(ValidationError):
            MergeClustersRequest(cluster_ids=[uuid4()])
