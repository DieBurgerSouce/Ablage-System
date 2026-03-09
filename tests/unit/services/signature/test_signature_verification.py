# -*- coding: utf-8 -*-
"""Unit tests for SignatureService dataclasses and verification logic."""

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.signature.signature_service import (
    SignerInfo,
    SignatureService,
    SignatureVerificationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> SignatureService:
    return SignatureService()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# SignerInfo dataclass
# ---------------------------------------------------------------------------


class TestSignerInfo:
    def test_creation_with_required_fields(self) -> None:
        signer = SignerInfo(email="max@example.com", name="Max Mustermann")
        assert signer.email == "max@example.com"
        assert signer.name == "Max Mustermann"
        assert signer.user_id is None
        assert signer.signing_order == 1

    def test_creation_with_all_fields(self) -> None:
        uid = uuid4()
        signer = SignerInfo(
            email="anna@example.com",
            name="Anna Schmidt",
            user_id=uid,
            signing_order=3,
        )
        assert signer.user_id == uid
        assert signer.signing_order == 3

    def test_default_signing_order_is_one(self) -> None:
        signer = SignerInfo(email="a@b.com", name="A")
        assert signer.signing_order == 1


# ---------------------------------------------------------------------------
# SignatureVerificationResult dataclass
# ---------------------------------------------------------------------------


class TestSignatureVerificationResult:
    def test_creation_with_defaults(self) -> None:
        doc_id = uuid4()
        result = SignatureVerificationResult(
            document_id=doc_id,
            is_fully_signed=True,
            total_signatures=2,
            completed_signatures=2,
            pending_signatures=0,
            rejected_signatures=0,
        )
        assert result.document_id == doc_id
        assert result.is_fully_signed is True
        assert result.signatures == []

    def test_creation_with_signatures(self) -> None:
        doc_id = uuid4()
        sigs = [
            {"entry_id": str(uuid4()), "status": "signed"},
            {"entry_id": str(uuid4()), "status": "pending"},
        ]
        result = SignatureVerificationResult(
            document_id=doc_id,
            is_fully_signed=False,
            total_signatures=2,
            completed_signatures=1,
            pending_signatures=1,
            rejected_signatures=0,
            signatures=sigs,
        )
        assert len(result.signatures) == 2

    def test_fully_signed_when_all_complete(self) -> None:
        result = SignatureVerificationResult(
            document_id=uuid4(),
            is_fully_signed=True,
            total_signatures=3,
            completed_signatures=3,
            pending_signatures=0,
            rejected_signatures=0,
        )
        assert result.is_fully_signed is True

    def test_not_fully_signed_with_pending(self) -> None:
        result = SignatureVerificationResult(
            document_id=uuid4(),
            is_fully_signed=False,
            total_signatures=3,
            completed_signatures=2,
            pending_signatures=1,
            rejected_signatures=0,
        )
        assert result.is_fully_signed is False

    def test_not_fully_signed_with_rejections(self) -> None:
        result = SignatureVerificationResult(
            document_id=uuid4(),
            is_fully_signed=False,
            total_signatures=3,
            completed_signatures=2,
            pending_signatures=0,
            rejected_signatures=1,
        )
        assert result.is_fully_signed is False

    def test_zero_signatures_not_fully_signed(self) -> None:
        """Empty document with no signatures is not fully signed."""
        result = SignatureVerificationResult(
            document_id=uuid4(),
            is_fully_signed=False,
            total_signatures=0,
            completed_signatures=0,
            pending_signatures=0,
            rejected_signatures=0,
        )
        assert result.is_fully_signed is False


# ---------------------------------------------------------------------------
# verify_signatures (integration with mock DB)
# ---------------------------------------------------------------------------


class TestVerifySignatures:
    @pytest.mark.asyncio
    async def test_no_requests_returns_empty_verification(
        self, service: SignatureService, mock_db: AsyncMock
    ) -> None:
        """Document with no signature requests should not be fully signed."""
        doc_id = uuid4()
        company_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.verify_signatures(mock_db, doc_id, company_id)

        assert isinstance(result, SignatureVerificationResult)
        assert result.document_id == doc_id
        assert result.is_fully_signed is False
        assert result.total_signatures == 0
        assert result.completed_signatures == 0

    @pytest.mark.asyncio
    async def test_all_signed_returns_fully_signed(
        self, service: SignatureService, mock_db: AsyncMock
    ) -> None:
        """All entries signed -> is_fully_signed = True."""
        doc_id = uuid4()
        company_id = uuid4()

        entry1 = MagicMock()
        entry1.id = uuid4()
        entry1.status = "signed"
        entry1.signer_name = "Max"
        entry1.signer_email = "max@test.de"
        entry1.signed_at = MagicMock()
        entry1.signed_at.isoformat.return_value = "2026-03-10T10:00:00"
        entry1.certificate_issuer = "TestCA"
        entry1.signature_hash = "abc123"

        entry2 = MagicMock()
        entry2.id = uuid4()
        entry2.status = "signed"
        entry2.signer_name = "Anna"
        entry2.signer_email = "anna@test.de"
        entry2.signed_at = MagicMock()
        entry2.signed_at.isoformat.return_value = "2026-03-10T11:00:00"
        entry2.certificate_issuer = "TestCA"
        entry2.signature_hash = "def456"

        request = MagicMock()
        request.entries = [entry1, entry2]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [request]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.verify_signatures(mock_db, doc_id, company_id)

        assert result.is_fully_signed is True
        assert result.total_signatures == 2
        assert result.completed_signatures == 2
        assert result.pending_signatures == 0
        assert result.rejected_signatures == 0
        assert len(result.signatures) == 2

    @pytest.mark.asyncio
    async def test_mixed_states(
        self, service: SignatureService, mock_db: AsyncMock
    ) -> None:
        """Mixed signed/pending/rejected entries."""
        doc_id = uuid4()
        company_id = uuid4()

        signed = MagicMock()
        signed.id = uuid4()
        signed.status = "signed"
        signed.signer_name = "A"
        signed.signer_email = "a@t.de"
        signed.signed_at = MagicMock()
        signed.signed_at.isoformat.return_value = "2026-03-10T10:00:00"
        signed.certificate_issuer = None
        signed.signature_hash = "hash1"

        pending = MagicMock()
        pending.id = uuid4()
        pending.status = "pending"
        pending.signer_name = "B"
        pending.signer_email = "b@t.de"
        pending.signed_at = None
        pending.certificate_issuer = None
        pending.signature_hash = None

        rejected = MagicMock()
        rejected.id = uuid4()
        rejected.status = "rejected"
        rejected.signer_name = "C"
        rejected.signer_email = "c@t.de"
        rejected.signed_at = None
        rejected.certificate_issuer = None
        rejected.signature_hash = None

        request = MagicMock()
        request.entries = [signed, pending, rejected]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [request]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.verify_signatures(mock_db, doc_id, company_id)

        assert result.is_fully_signed is False
        assert result.total_signatures == 3
        assert result.completed_signatures == 1
        assert result.pending_signatures == 1
        assert result.rejected_signatures == 1

    @pytest.mark.asyncio
    async def test_multiple_requests_aggregated(
        self, service: SignatureService, mock_db: AsyncMock
    ) -> None:
        """Entries from multiple requests should be aggregated."""
        doc_id = uuid4()
        company_id = uuid4()

        entry1 = MagicMock()
        entry1.id = uuid4()
        entry1.status = "signed"
        entry1.signer_name = "X"
        entry1.signer_email = "x@t.de"
        entry1.signed_at = MagicMock()
        entry1.signed_at.isoformat.return_value = "2026-03-10T10:00:00"
        entry1.certificate_issuer = None
        entry1.signature_hash = "h1"

        entry2 = MagicMock()
        entry2.id = uuid4()
        entry2.status = "pending"
        entry2.signer_name = "Y"
        entry2.signer_email = "y@t.de"
        entry2.signed_at = None
        entry2.certificate_issuer = None
        entry2.signature_hash = None

        req1 = MagicMock()
        req1.entries = [entry1]
        req2 = MagicMock()
        req2.entries = [entry2]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [req1, req2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.verify_signatures(mock_db, doc_id, company_id)

        assert result.total_signatures == 2
        assert result.completed_signatures == 1
        assert result.pending_signatures == 1
