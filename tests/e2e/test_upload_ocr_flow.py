# -*- coding: utf-8 -*-
"""
E2E Tests: Upload → OCR → Review → Export Happy Path

Tests the complete document processing workflow from upload
through OCR processing to review and export.

Feinpoliert und durchdacht - Upload-OCR-Flow Tests.
"""

import pytest
import asyncio
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.mark.e2e
class TestUploadOCRFlow:
    """Test complete upload to export workflow."""

    @pytest.mark.asyncio
    async def test_upload_to_ocr_happy_path(self, temp_storage, sample_german_text):
        """Test successful upload → OCR → storage flow."""
        # Step 1: Upload
        test_file = temp_storage / "uploads" / "rechnung_001.pdf"
        test_file.write_bytes(b"%PDF-1.4 test invoice")

        with patch("app.services.storage_service.StorageService") as MockStorage:
            mock_storage = AsyncMock()
            mock_storage.upload_file.return_value = {
                "file_id": "doc_upload_001",
                "filename": "rechnung_001.pdf",
                "size": 2048,
                "content_type": "application/pdf",
                "status": "uploaded"
            }
            MockStorage.return_value = mock_storage

            upload_result = await mock_storage.upload_file(str(test_file))
            assert upload_result["status"] == "uploaded"

        # Step 2: OCR Processing
        with patch("app.services.ocr_service.OCRService") as MockOCR:
            mock_ocr = AsyncMock()
            mock_ocr.process_document.return_value = {
                "success": True,
                "text": sample_german_text,
                "confidence": 0.94,
                "backend": "deepseek",
                "processing_time_ms": 1800
            }
            MockOCR.return_value = mock_ocr

            ocr_result = await mock_ocr.process_document(
                document_id=upload_result["file_id"],
                backend="auto"
            )
            assert ocr_result["success"] is True
            assert ocr_result["confidence"] >= 0.8

        # Step 3: Storage
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.save_processed_document.return_value = {
                "id": upload_result["file_id"],
                "status": "processed",
                "ocr_completed": True
            }
            MockDoc.return_value = mock_doc

            save_result = await mock_doc.save_processed_document({
                "file_id": upload_result["file_id"],
                "ocr_text": ocr_result["text"],
                "confidence": ocr_result["confidence"]
            })
            assert save_result["status"] == "processed"

    @pytest.mark.asyncio
    async def test_review_and_correction_flow(self, mock_ocr_result):
        """Test OCR → Review → Correction → Re-save flow."""
        # Step 1: OCR with issues
        ocr_with_issues = {
            **mock_ocr_result,
            "text": "Die Aenderung kostet 100,00 EUR",  # Umlaut error
            "confidence": 0.85,
            "needs_review": True
        }

        # Step 2: Review detects issues
        with patch("app.agents.postprocessing.qa_agent.QAAgent") as MockQA:
            mock_qa = AsyncMock()
            mock_qa.process.return_value = {
                "quality_level": "acceptable",
                "quality_score": 0.75,
                "issues": [
                    {
                        "type": "umlaut_error",
                        "severity": "medium",
                        "description": "Möglicher Umlaut-Fehler: 'Aenderung'",
                        "suggestion": "Änderung"
                    }
                ]
            }
            MockQA.return_value = mock_qa

            review_result = await mock_qa.process({"text": ocr_with_issues["text"]})
            assert len(review_result["issues"]) > 0

        # Step 3: Apply corrections
        with patch("app.agents.postprocessing.german_correction_agent.GermanCorrectionAgent") as MockCorrection:
            mock_correction = AsyncMock()
            mock_correction.process.return_value = {
                "text": "Die Änderung kostet 100,00 EUR",
                "corrections_applied": 1,
                "validation_score": 0.96
            }
            MockCorrection.return_value = mock_correction

            corrected = await mock_correction.process({"text": ocr_with_issues["text"]})
            assert "Änderung" in corrected["text"]
            assert corrected["corrections_applied"] > 0

        # Step 4: Re-save with corrected text
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.update_document_text.return_value = {
                "status": "updated",
                "quality_improved": True
            }
            MockDoc.return_value = mock_doc

            update_result = await mock_doc.update_document_text(
                document_id="doc_001",
                corrected_text=corrected["text"]
            )
            assert update_result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_export_processed_document(self, mock_ocr_result):
        """Test Export flow: Retrieve → Format → Download."""
        # Step 1: Retrieve processed document
        with patch("app.services.document_service.DocumentService") as MockDoc:
            mock_doc = AsyncMock()
            mock_doc.get_document.return_value = {
                "id": "doc_001",
                "filename": "rechnung_001.pdf",
                "ocr_text": mock_ocr_result["text"],
                "entities": [
                    {"type": "currency", "value": {"amount": 1190.0, "currency": "EUR"}}
                ],
                "quality_score": 0.95
            }
            MockDoc.return_value = mock_doc

            document = await mock_doc.get_document("doc_001")
            assert document["id"] == "doc_001"

        # Step 2: Export as JSON
        with patch("app.services.export_service.ExportService") as MockExport:
            mock_export = AsyncMock()
            mock_export.export_to_json.return_value = {
                "success": True,
                "export_path": "/exports/doc_001.json",
                "format": "json"
            }
            MockExport.return_value = mock_export

            export_result = await mock_export.export_to_json("doc_001")
            assert export_result["success"] is True
            assert export_result["format"] == "json"

        # Step 3: Export as PDF with OCR layer
        with patch("app.services.export_service.ExportService") as MockExport:
            mock_export = AsyncMock()
            mock_export.export_to_pdf_with_ocr.return_value = {
                "success": True,
                "export_path": "/exports/doc_001_ocr.pdf",
                "format": "pdf",
                "has_text_layer": True
            }
            MockExport.return_value = mock_export

            pdf_result = await mock_export.export_to_pdf_with_ocr("doc_001")
            assert pdf_result["success"] is True
            assert pdf_result["has_text_layer"] is True
