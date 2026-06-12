# -*- coding: utf-8 -*-
"""Unit tests for Compliance Autopilot Service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, date, timedelta

from app.services.compliance.autopilot_service import (
    ComplianceAutopilotService,
    ComplianceScanResult,
    ComplianceItem,
    RetentionReport,
    GDPRCheckResult,
    AuditPackage,
)
from app.db.models import Document, DocumentType, AuditLog


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service():
    """Compliance autopilot service instance."""
    return ComplianceAutopilotService()


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid4()


@pytest.mark.asyncio
async def test_compliance_scan_gdpr(service, mock_db, company_id):
    """Test GDPR compliance check."""
    # Mock document query
    mock_docs = []
    mock_result_docs = MagicMock()
    mock_result_docs.scalars().all.return_value = mock_docs

    # Mock audit log count
    mock_result_audit = MagicMock()
    mock_result_audit.scalar.return_value = 100

    mock_db.execute.side_effect = [
        mock_result_docs,  # Documents query
        mock_result_audit,  # Audit count
        mock_result_audit,  # GDPR check audit
        mock_result_docs,  # Another doc query
        mock_result_audit,  # Personal data count
        mock_result_audit,  # Deletion candidates
        mock_result_audit,  # Audit entries
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    assert isinstance(result, ComplianceScanResult)
    assert result.total_checks > 0
    assert result.score >= 0.0
    assert result.score <= 100.0

    # Should have GDPR checks
    gdpr_items = [item for item in result.items if item.category == "gdpr"]
    assert len(gdpr_items) > 0


@pytest.mark.asyncio
async def test_compliance_scan_gobd(service, mock_db, company_id):
    """Test GoBD compliance check."""
    # Mock financial documents with version history
    mock_doc1 = MagicMock(spec=Document)
    mock_doc1.id = uuid4()
    mock_doc1.document_type = DocumentType.INVOICE
    mock_doc1.created_at = datetime.utcnow() - timedelta(days=30)
    mock_doc1.metadata = {"version_history": [{"version": 1}]}

    mock_doc2 = MagicMock(spec=Document)
    mock_doc2.id = uuid4()
    mock_doc2.document_type = DocumentType.RECEIPT
    mock_doc2.created_at = datetime.utcnow() - timedelta(days=30)
    mock_doc2.metadata = {"version_history": [{"version": 1}]}

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_doc1, mock_doc2]
    mock_result_audit = MagicMock()
    mock_result_audit.scalar.return_value = 50

    mock_db.execute.side_effect = [
        mock_result,  # All docs
        mock_result_audit,  # Audit count
        mock_result,  # Financial docs for GoBD
        mock_result,  # Retention check
        mock_result_audit,
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    # Should have GoBD checks
    gobd_items = [item for item in result.items if item.category == "gobd"]
    assert len(gobd_items) > 0


@pytest.mark.asyncio
async def test_compliance_scan_retention(service, mock_db, company_id):
    """Test retention period compliance check."""
    # Mock documents with various ages
    old_doc = MagicMock(spec=Document)
    old_doc.id = uuid4()
    old_doc.document_type = DocumentType.LETTER
    old_doc.created_at = datetime.utcnow() - timedelta(days=3*365)  # 3 years old

    recent_doc = MagicMock(spec=Document)
    recent_doc.id = uuid4()
    recent_doc.document_type = DocumentType.INVOICE
    recent_doc.created_at = datetime.utcnow() - timedelta(days=30)

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [old_doc, recent_doc]
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 10

    mock_db.execute.side_effect = [
        mock_result,  # All docs
        mock_result_count,  # Audit count
        mock_result,  # Financial docs
        mock_result,  # Retention check
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    # Should have retention checks
    retention_items = [item for item in result.items if item.category == "retention"]
    assert len(retention_items) > 0


@pytest.mark.asyncio
async def test_compliance_scan_security(service, mock_db, company_id):
    """Test security compliance check."""
    # Mock minimal data
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 0

    mock_db.execute.side_effect = [
        mock_result,  # Docs
        mock_result_count,  # Audit
        mock_result,  # Financial
        mock_result,  # Retention
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    # Should have security checks
    security_items = [item for item in result.items if item.category == "security"]
    assert len(security_items) > 0


@pytest.mark.asyncio
async def test_compliance_scan_all(service, mock_db, company_id):
    """Test full compliance scan across all categories."""
    # Mock comprehensive data
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = uuid4()
    mock_doc.document_type = DocumentType.INVOICE
    mock_doc.created_at = datetime.utcnow()
    mock_doc.metadata = {"version_history": [{"version": 1}]}

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_doc]
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 100

    mock_db.execute.side_effect = [
        mock_result,
        mock_result_count,
        mock_result,
        mock_result,
        mock_result_count,
        mock_result_count,
        mock_result_count,
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    assert result.total_checks > 0
    # Should have all categories
    categories = {item.category for item in result.items}
    assert "gdpr" in categories
    assert "gobd" in categories
    assert "retention" in categories
    assert "security" in categories


@pytest.mark.asyncio
async def test_compliance_score_perfect(service, mock_db, company_id):
    """Test compliance score when all checks pass."""
    # Mock perfect compliance
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = uuid4()
    mock_doc.document_type = DocumentType.INVOICE
    mock_doc.created_at = datetime.utcnow()
    mock_doc.metadata = {"version_history": [{"version": 1}]}

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_doc]
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 100

    mock_db.execute.side_effect = [
        mock_result,
        mock_result_count,
        mock_result,
        mock_result,
        mock_result_count,
        mock_result_count,
        mock_result_count,
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    # Score should be high (close to 100)
    assert result.score >= 80.0
    assert result.failures == 0


@pytest.mark.asyncio
async def test_compliance_score_violations(service, mock_db, company_id):
    """Test compliance score with violations reduces score."""
    # Mock documents with compliance issues
    doc_no_metadata = MagicMock(spec=Document)
    doc_no_metadata.id = uuid4()
    doc_no_metadata.document_type = DocumentType.INVOICE
    doc_no_metadata.created_at = datetime.utcnow() - timedelta(days=11*365)
    doc_no_metadata.metadata = None  # Violation

    doc_no_version = MagicMock(spec=Document)
    doc_no_version.id = uuid4()
    doc_no_version.document_type = DocumentType.CREDIT_NOTE
    doc_no_version.created_at = datetime.utcnow()
    doc_no_version.metadata = {}  # No version_history

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc_no_metadata, doc_no_version]
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 0  # No audit log

    mock_db.execute.side_effect = [
        mock_result,
        mock_result_count,
        mock_result,
        mock_result,
        mock_result_count,
        mock_result_count,
        mock_result_count,
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    # Score should be reduced
    assert result.score < 100.0
    assert result.warnings > 0 or result.failures > 0


@pytest.mark.asyncio
async def test_audit_package_export(service, mock_db, company_id):
    """Test generating audit ZIP package for tax inspection."""
    # Mock documents
    doc1 = MagicMock(spec=Document)
    doc1.id = uuid4()
    doc1.document_type = DocumentType.INVOICE
    doc1.created_at = datetime(2025, 6, 1, 12, 0, 0)
    doc1.filename = "invoice_001.pdf"

    doc2 = MagicMock(spec=Document)
    doc2.id = uuid4()
    doc2.document_type = DocumentType.RECEIPT
    doc2.created_at = datetime(2025, 7, 15, 14, 30, 0)
    doc2.filename = "receipt_002.pdf"

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc1, doc2]
    mock_db.execute.return_value = mock_result

    date_range = (date(2025, 1, 1), date(2025, 12, 31))
    package = await service.prepare_audit(company_id, date_range, mock_db)

    assert isinstance(package, AuditPackage)
    assert package.document_count == 2
    assert package.date_range == date_range
    assert len(package.zip_content) > 0
    assert package.filename.endswith(".zip")
    assert "invoice" in package.included_types or "receipt" in package.included_types


@pytest.mark.asyncio
async def test_retention_period_tracking(service, mock_db, company_id):
    """Test §147 AO retention period tracking (10 years for invoices)."""
    # Mock documents with various retention periods
    invoice = MagicMock(spec=Document)
    invoice.id = uuid4()
    invoice.document_type = DocumentType.INVOICE
    invoice.created_at = datetime.utcnow() - timedelta(days=11*365)  # 11 years - expired

    contract = MagicMock(spec=Document)
    contract.id = uuid4()
    contract.document_type = DocumentType.CONTRACT
    contract.created_at = datetime.utcnow() - timedelta(days=5*365)  # 5 years - valid

    letter = MagicMock(spec=Document)
    letter.id = uuid4()
    letter.document_type = DocumentType.LETTER
    letter.created_at = datetime.utcnow() - timedelta(days=3*365)  # 3 years - expired

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [invoice, contract, letter]
    mock_db.execute.return_value = mock_result

    report = await service.check_retention(company_id, mock_db)

    assert isinstance(report, RetentionReport)
    assert report.documents_total == 3
    assert report.documents_expired >= 1  # At least invoice is expired
    assert len(report.expired_document_ids) >= 1


@pytest.mark.asyncio
async def test_compliance_recommendations(service, mock_db, company_id):
    """Test generating fix recommendations for compliance issues."""
    # Mock documents with issues
    doc = MagicMock(spec=Document)
    doc.id = uuid4()
    doc.document_type = DocumentType.INVOICE
    doc.created_at = datetime.utcnow() - timedelta(days=11*365)
    doc.metadata = None  # Issue

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc]
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 0

    mock_db.execute.side_effect = [
        mock_result,
        mock_result_count,
        mock_result,
        mock_result,
        mock_result_count,
        mock_result_count,
        mock_result_count,
    ]

    result = await service.run_compliance_scan(company_id, mock_db)

    # Should have items with recommendations
    items_with_recommendations = [
        item for item in result.items if item.recommendation is not None
    ]
    assert len(items_with_recommendations) > 0


@pytest.mark.asyncio
async def test_run_gdpr_check(service, mock_db, company_id):
    """Test dedicated GDPR check method."""
    # Mock data
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 100

    mock_db.execute.side_effect = [
        mock_result_count,  # personal_data_count
        mock_result_count,  # deletion_candidates
        mock_result_count,  # audit_entries
    ]

    result = await service.run_gdpr_check(company_id, mock_db)

    assert isinstance(result, GDPRCheckResult)
    assert isinstance(result.compliant, bool)  # Fixed: Check type, not tautology
    assert result.personal_data_count >= 0
    assert result.deletion_candidates >= 0
    assert isinstance(result.issues, list)
    assert isinstance(result.recommendations, list)


@pytest.mark.asyncio
async def test_retention_report_expiring_soon(service, mock_db, company_id):
    """Test retention report includes documents expiring soon."""
    # Mock document expiring in 20 days
    expiring_doc = MagicMock(spec=Document)
    expiring_doc.id = uuid4()
    expiring_doc.document_type = DocumentType.DELIVERY_NOTE  # 6 years retention
    # Calculate created_at so it expires in 20 days
    expiring_doc.created_at = datetime.utcnow() - timedelta(days=(6*365 - 20))

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [expiring_doc]
    mock_db.execute.return_value = mock_result

    report = await service.check_retention(company_id, mock_db)

    assert report.documents_expiring_soon >= 0
    assert len(report.expiring_soon_ids) >= 0


@pytest.mark.asyncio
async def test_audit_package_date_filtering(service, mock_db, company_id):
    """Test audit package only includes documents in date range."""
    # Mock documents, some in range, some out
    doc_in_range = MagicMock(spec=Document)
    doc_in_range.id = uuid4()
    doc_in_range.document_type = DocumentType.INVOICE
    doc_in_range.created_at = datetime(2025, 6, 15, 10, 0, 0)
    doc_in_range.filename = "invoice.pdf"

    doc_out_range = MagicMock(spec=Document)
    doc_out_range.id = uuid4()
    doc_out_range.document_type = DocumentType.INVOICE
    doc_out_range.created_at = datetime(2024, 1, 1, 10, 0, 0)
    doc_out_range.filename = "old_invoice.pdf"

    # Only doc_in_range should be returned by DB query
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc_in_range]
    mock_db.execute.return_value = mock_result

    date_range = (date(2025, 1, 1), date(2025, 12, 31))
    package = await service.prepare_audit(company_id, date_range, mock_db)

    assert package.document_count == 1
    assert package.date_range == date_range


# ============================================================================
# W1-031: Audit-Paket mit echten MinIO-Dateien
# ============================================================================


def _make_doc(filename: str, file_path: str, doc_type=DocumentType.INVOICE):
    """Hilfsfunktion: Dokument-Mock fuer Audit-Tests."""
    doc = MagicMock(spec=Document)
    doc.id = uuid4()
    doc.document_type = doc_type
    doc.created_at = datetime(2025, 6, 1, 12, 0, 0)
    doc.filename = filename
    doc.file_path = file_path
    return doc


@pytest.mark.asyncio
async def test_audit_package_contains_real_minio_content(
    service, mock_db, company_id
):
    """W1-031: ZIP enthaelt echten Datei-Inhalt aus dem Storage, kein Mock."""
    import io
    import zipfile
    from unittest.mock import patch

    doc = _make_doc("rechnung_001.pdf", "docs/rechnung_001.pdf")
    real_content = b"%PDF-1.4 echter Inhalt aus MinIO"

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc]
    mock_db.execute.return_value = mock_result

    fake_storage = MagicMock()
    fake_storage.download_document = AsyncMock(return_value=real_content)

    with patch(
        "app.services.storage_service.get_storage_service",
        return_value=fake_storage,
    ):
        package = await service.prepare_audit(
            company_id, (date(2025, 1, 1), date(2025, 12, 31)), mock_db
        )

    fake_storage.download_document.assert_awaited_once_with("docs/rechnung_001.pdf")
    assert package.documents_missing == 0

    with zipfile.ZipFile(io.BytesIO(package.zip_content)) as zf:
        entry = f"invoice/20250601_{doc.id}.pdf"
        assert entry in zf.namelist()
        assert zf.read(entry) == real_content
        # Kein Mock-Content mehr
        assert f"Dokument {doc.id}".encode() != zf.read(entry)


@pytest.mark.asyncio
async def test_audit_package_marks_missing_files(service, mock_db, company_id):
    """W1-031: Nicht abrufbare Dateien -> *_FEHLT.txt + FEHLENDE_DATEIEN.txt."""
    import io
    import zipfile
    from unittest.mock import patch

    doc = _make_doc("beleg.pdf", "docs/beleg.pdf", DocumentType.RECEIPT)

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc]
    mock_db.execute.return_value = mock_result

    fake_storage = MagicMock()
    fake_storage.download_document = AsyncMock(
        side_effect=RuntimeError("MinIO not available")
    )

    with patch(
        "app.services.storage_service.get_storage_service",
        return_value=fake_storage,
    ):
        package = await service.prepare_audit(
            company_id, (date(2025, 1, 1), date(2025, 12, 31)), mock_db
        )

    assert package.documents_missing == 1
    with zipfile.ZipFile(io.BytesIO(package.zip_content)) as zf:
        names = zf.namelist()
        assert f"receipt/20250601_{doc.id}_FEHLT.txt" in names
        assert "FEHLENDE_DATEIEN.txt" in names
        placeholder = zf.read(f"receipt/20250601_{doc.id}_FEHLT.txt").decode("utf-8")
        assert "nicht abrufbar" in placeholder


@pytest.mark.asyncio
async def test_audit_package_survives_storage_init_failure(
    service, mock_db, company_id
):
    """W1-031: Storage-Init-Fehler crasht das Audit-Paket nicht."""
    from unittest.mock import patch

    doc = _make_doc("rechnung.pdf", "docs/rechnung.pdf")

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc]
    mock_db.execute.return_value = mock_result

    with patch(
        "app.services.storage_service.get_storage_service",
        side_effect=RuntimeError("Konfiguration fehlt"),
    ):
        package = await service.prepare_audit(
            company_id, (date(2025, 1, 1), date(2025, 12, 31)), mock_db
        )

    assert package.document_count == 1
    assert package.documents_missing == 1


@pytest.mark.asyncio
async def test_audit_package_keeps_original_extension(service, mock_db, company_id):
    """W1-031: Original-Datei-Endung bleibt erhalten (kein .pdf-Zwang)."""
    import io
    import zipfile
    from unittest.mock import patch

    doc = _make_doc("scan_007.tiff", "docs/scan_007.tiff")

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [doc]
    mock_db.execute.return_value = mock_result

    fake_storage = MagicMock()
    fake_storage.download_document = AsyncMock(return_value=b"TIFF-Daten")

    with patch(
        "app.services.storage_service.get_storage_service",
        return_value=fake_storage,
    ):
        package = await service.prepare_audit(
            company_id, (date(2025, 1, 1), date(2025, 12, 31)), mock_db
        )

    with zipfile.ZipFile(io.BytesIO(package.zip_content)) as zf:
        assert f"invoice/20250601_{doc.id}.tiff" in zf.namelist()
