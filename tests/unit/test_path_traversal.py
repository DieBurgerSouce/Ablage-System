# -*- coding: utf-8 -*-
"""Tests for path traversal protection in document upload (CWE-22)."""

import pytest
from pydantic import ValidationError

from app.db.schemas import UploadCompleteRequest


class TestFilenamePathTraversal:
    """Test path traversal prevention in final_filename field."""

    BASE_VALID_DATA = {
        "temp_file_id": "test-123",
        "document_type": "invoice",
        "folder_id": "folie",
        "category": "rechnungen",
        "entity_type": "customer",
    }

    def _make_request(self, filename: str) -> UploadCompleteRequest:
        return UploadCompleteRequest(
            final_filename=filename,
            **self.BASE_VALID_DATA,
        )

    def test_valid_filename(self):
        req = self._make_request("rechnung_2024.pdf")
        assert req.final_filename == "rechnung_2024.pdf"

    def test_valid_filename_with_spaces(self):
        req = self._make_request("Rechnung Januar 2024.pdf")
        assert req.final_filename == "Rechnung Januar 2024.pdf"

    def test_path_traversal_dotdot(self):
        with pytest.raises(ValidationError, match="Pfad-Traversal"):
            self._make_request("../../etc/passwd")

    def test_path_traversal_forward_slash(self):
        with pytest.raises(ValidationError, match="Pfad-Traversal"):
            self._make_request("path/to/file.pdf")

    def test_path_traversal_backslash(self):
        with pytest.raises(ValidationError, match="Pfad-Traversal"):
            self._make_request("path\\to\\file.pdf")

    def test_null_byte_injection(self):
        with pytest.raises(ValidationError, match="Nullbytes"):
            self._make_request("file.pdf\x00.exe")

    def test_empty_filename_rejected(self):
        with pytest.raises(ValidationError):
            self._make_request("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            self._make_request("   ")

    def test_dotdot_in_middle(self):
        with pytest.raises(ValidationError, match="Pfad-Traversal"):
            self._make_request("legit..file.pdf/../../../etc/shadow")

    def test_windows_path_traversal(self):
        with pytest.raises(ValidationError, match="Pfad-Traversal"):
            self._make_request("..\\..\\windows\\system32\\config\\sam")
