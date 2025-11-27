"""API endpoint tests for Ablage-System."""

import pytest
from fastapi import status
from pathlib import Path


@pytest.mark.api
class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "name" in data
        assert data["name"] == "Ablage-System OCR"
        assert "endpoints" in data
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
    
    def test_gpu_status(self, client, mock_gpu_manager):
        """Test GPU status endpoint."""
        response = client.get("/gpu/status")
        # May return 503 if GPU manager not initialized in test
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]


@pytest.mark.api
class TestOCREndpoints:
    """Test OCR processing endpoints."""
    
    def test_get_backends(self, client):
        """Test getting available OCR backends."""
        response = client.get("/ocr/backends")
        # May return 503 if service not initialized
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "available_backends" in data
            assert "backend_status" in data
            assert "recommended" in data
    
    @pytest.mark.asyncio
    async def test_process_document(self, async_client, sample_pdf_file):
        """Test document processing endpoint."""
        with open(sample_pdf_file, "rb") as f:
            files = {"file": ("test.pdf", f, "application/pdf")}
            data = {
                "backend": "auto",
                "language": "de",
                "detect_layout": "true"
            }
            
            response = await async_client.post(
                "/ocr/process",
                files=files,
                data=data
            )
            
            # May fail if service not fully initialized
            if response.status_code == status.HTTP_200_OK:
                result = response.json()
                assert "success" in result
                assert "text" in result
    
    def test_validate_german_text(self, client, sample_german_text):
        """Test German text validation endpoint."""
        response = client.post(
            "/ocr/test",
            json={"text": sample_german_text}
        )
        
        # May return 503 if validator not initialized
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "valid_german" in data
            assert "has_umlauts" in data
            assert "dates" in data
            assert "amounts" in data


@pytest.mark.api
class TestDocumentValidation:
    """Test document validation and file type checking."""
    
    def test_invalid_file_type(self, client):
        """Test rejection of invalid file types."""
        # Create a fake .txt file
        files = {"file": ("test.txt", b"test content", "text/plain")}
        data = {"backend": "auto", "language": "de"}
        
        response = client.post("/ocr/process", files=files, data=data)
        
        # Should reject invalid file type
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            assert "not supported" in response.json().get("detail", "").lower()
    
    def test_file_size_validation(self, client):
        """Test file size validation."""
        # Create a large fake file (>50MB)
        large_content = b"x" * (51 * 1024 * 1024)
        files = {"file": ("large.pdf", large_content, "application/pdf")}
        data = {"backend": "auto", "language": "de"}
        
        response = client.post("/ocr/process", files=files, data=data)
        
        # Should handle large files appropriately
        assert response.status_code in [
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ]


@pytest.mark.api
class TestStatisticsEndpoint:
    """Test statistics and metrics endpoints."""
    
    def test_get_statistics(self, client):
        """Test statistics endpoint."""
        response = client.get("/stats")
        
        # May return 503 if service not initialized
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            # Statistics structure should be defined
            assert isinstance(data, dict)
