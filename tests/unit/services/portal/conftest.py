# -*- coding: utf-8 -*-
"""
Fixtures fuer Portal Services Unit Tests.

Stellt bereit:
- Mock PortalUser, PortalSession
- Mock InvoiceTracking
- AsyncSession Mock
- Sample Data Generators

Feinpoliert und durchdacht - Portal Test Fixtures.
"""

from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock
from uuid import UUID, uuid4
import secrets

import pytest
import pytest_asyncio

from app.db.models_portal import (
    PortalUser,
    PortalSession,
    PortalComplaint,
    PortalMessage,
    PortalDocument,
    PortalPaymentConfirmation,
    PortalUserStatus,
    ComplaintStatus,
    ComplaintType,
    MessageDirection,
)


# ========================= ID Fixtures =========================


@pytest.fixture
def company_id() -> UUID:
    """Fixed company ID for tests."""
    return UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def entity_id() -> UUID:
    """Fixed entity ID for tests."""
    return UUID("abcdef12-3456-7890-abcd-ef1234567890")


@pytest.fixture
def other_entity_id() -> UUID:
    """Different entity ID for isolation tests."""
    return UUID("99999999-9999-9999-9999-999999999999")


@pytest.fixture
def portal_user_id() -> UUID:
    """Fixed portal user ID for tests."""
    return UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def invoice_id() -> UUID:
    """Fixed invoice ID for tests."""
    return UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def document_id() -> UUID:
    """Fixed document ID for tests."""
    return UUID("dddddddd-eeee-ffff-0000-111111111111")


# ========================= AsyncSession Mock =========================


@pytest.fixture
def mock_db() -> AsyncMock:
    """
    Provide AsyncSession mock.

    Can be configured per test for specific query results.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


def create_mock_result(scalar_value: Any = None, scalars_list: Optional[List] = None):
    """
    Helper to create mock result for db.execute().

    Args:
        scalar_value: Value for result.scalar_one_or_none()
        scalars_list: List for result.scalars().all()
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    result.scalar = MagicMock(return_value=scalar_value)

    if scalars_list is not None:
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=scalars_list)
        result.scalars = MagicMock(return_value=scalars_mock)
    else:
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    return result


# ========================= PortalUser Fixtures =========================


@pytest.fixture
def sample_portal_user(company_id: UUID, entity_id: UUID, portal_user_id: UUID) -> PortalUser:
    """
    Provide active PortalUser for tests.
    """
    user = MagicMock(spec=PortalUser)
    user.id = portal_user_id
    user.entity_id = entity_id
    user.company_id = company_id
    user.email = "kunde@beispiel.de"
    user.hashed_password = "$2b$12$testhashedpassword"
    user.first_name = "Max"
    user.last_name = "Mustermann"
    user.phone = "+49 30 12345678"
    user.position = "Einkaufsleiter"
    user.status = PortalUserStatus.ACTIVE
    user.can_view_invoices = True
    user.can_confirm_payments = True
    user.can_submit_complaints = True
    user.can_upload_documents = True
    user.can_view_all_entity_data = False
    user.invitation_token = None
    user.invitation_sent_at = None
    user.invitation_expires_at = None
    user.invited_by_id = uuid4()
    user.password_changed_at = datetime.now(timezone.utc) - timedelta(days=30)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc) - timedelta(hours=1)
    user.created_at = datetime.now(timezone.utc) - timedelta(days=90)
    user.updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    return user


@pytest.fixture
def pending_portal_user(company_id: UUID, entity_id: UUID) -> PortalUser:
    """
    Provide pending PortalUser awaiting activation.
    """
    user = MagicMock(spec=PortalUser)
    user.id = uuid4()
    user.entity_id = entity_id
    user.company_id = company_id
    user.email = "neukunde@beispiel.de"
    user.hashed_password = ""
    user.first_name = "Anna"
    user.last_name = "Schmidt"
    user.status = PortalUserStatus.PENDING
    user.invitation_token = secrets.token_hex(32)
    user.invitation_sent_at = datetime.now(timezone.utc) - timedelta(hours=2)
    user.invitation_expires_at = datetime.now(timezone.utc) + timedelta(days=6)
    user.failed_login_attempts = 0
    user.locked_until = None
    return user


@pytest.fixture
def locked_portal_user(company_id: UUID, entity_id: UUID) -> PortalUser:
    """
    Provide locked PortalUser (too many failed attempts).
    """
    user = MagicMock(spec=PortalUser)
    user.id = uuid4()
    user.entity_id = entity_id
    user.company_id = company_id
    user.email = "gesperrt@beispiel.de"
    user.hashed_password = "$2b$12$testhashedpassword"
    user.status = PortalUserStatus.ACTIVE
    user.failed_login_attempts = 5
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=20)
    return user


# ========================= PortalSession Fixtures =========================


@pytest.fixture
def sample_portal_session(portal_user_id: UUID) -> PortalSession:
    """
    Provide valid PortalSession.
    """
    session = MagicMock(spec=PortalSession)
    session.id = uuid4()
    session.portal_user_id = portal_user_id
    session.session_token_hash = secrets.token_hex(32)
    session.refresh_token_hash = secrets.token_hex(32)
    session.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    session.ip_address = "192.168.1.100"
    session.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)
    session.refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=6)
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    session.revoked_at = None
    session.revoked_reason = None
    return session


@pytest.fixture
def expired_portal_session(portal_user_id: UUID) -> PortalSession:
    """
    Provide expired PortalSession.
    """
    session = MagicMock(spec=PortalSession)
    session.id = uuid4()
    session.portal_user_id = portal_user_id
    session.session_token_hash = secrets.token_hex(32)
    session.refresh_token_hash = secrets.token_hex(32)
    session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=5)
    session.revoked_at = None
    return session


# ========================= InvoiceTracking Fixtures =========================


@pytest.fixture
def sample_invoice_tracking(company_id: UUID, entity_id: UUID, invoice_id: UUID, document_id: UUID):
    """
    Provide sample InvoiceTracking (mocked).
    """
    invoice = MagicMock()
    invoice.id = invoice_id
    invoice.entity_id = entity_id
    invoice.company_id = company_id
    invoice.document_id = document_id
    invoice.invoice_number = "RE-2026-00123"
    invoice.invoice_date = date.today() - timedelta(days=14)
    invoice.due_date = date.today() + timedelta(days=16)
    invoice.gross_amount = Decimal("1190.00")
    invoice.net_amount = Decimal("1000.00")
    invoice.vat_amount = Decimal("190.00")
    invoice.currency = "EUR"
    invoice.status = "open"
    invoice.dunning_level = 0
    invoice.paid_amount = Decimal("0.00")
    invoice.outstanding_amount = Decimal("1190.00")
    invoice.skonto_percentage = Decimal("2.0")
    invoice.skonto_days = 10
    invoice.skonto_deadline = date.today() - timedelta(days=4)
    invoice.skonto_amount = Decimal("23.80")
    invoice.partial_payments = []
    invoice.created_at = datetime.now(timezone.utc) - timedelta(days=14)
    invoice.updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    invoice.paid_at = None
    invoice.document = MagicMock()
    return invoice


@pytest.fixture
def overdue_invoice(company_id: UUID, entity_id: UUID):
    """
    Provide overdue InvoiceTracking.
    """
    invoice = MagicMock()
    invoice.id = uuid4()
    invoice.entity_id = entity_id
    invoice.company_id = company_id
    invoice.document_id = uuid4()
    invoice.invoice_number = "RE-2025-00099"
    invoice.invoice_date = date.today() - timedelta(days=60)
    invoice.due_date = date.today() - timedelta(days=30)
    invoice.gross_amount = Decimal("595.00")
    invoice.net_amount = Decimal("500.00")
    invoice.currency = "EUR"
    invoice.status = "overdue"
    invoice.dunning_level = 1
    invoice.paid_amount = Decimal("0.00")
    invoice.outstanding_amount = Decimal("595.00")
    invoice.skonto_percentage = None
    invoice.skonto_deadline = None
    invoice.skonto_amount = None
    invoice.partial_payments = []
    invoice.document = MagicMock()
    return invoice


@pytest.fixture
def paid_invoice(company_id: UUID, entity_id: UUID):
    """
    Provide paid InvoiceTracking.
    """
    invoice = MagicMock()
    invoice.id = uuid4()
    invoice.entity_id = entity_id
    invoice.company_id = company_id
    invoice.invoice_number = "RE-2026-00100"
    invoice.invoice_date = date.today() - timedelta(days=45)
    invoice.due_date = date.today() - timedelta(days=15)
    invoice.gross_amount = Decimal("2380.00")
    invoice.net_amount = Decimal("2000.00")
    invoice.currency = "EUR"
    invoice.status = "paid"
    invoice.dunning_level = 0
    invoice.paid_amount = Decimal("2380.00")
    invoice.outstanding_amount = Decimal("0.00")
    invoice.paid_at = datetime.now(timezone.utc) - timedelta(days=20)
    invoice.document = MagicMock()
    return invoice


# ========================= PortalComplaint Fixtures =========================


@pytest.fixture
def sample_complaint(company_id: UUID, entity_id: UUID, portal_user_id: UUID) -> PortalComplaint:
    """
    Provide sample PortalComplaint.
    """
    complaint = MagicMock(spec=PortalComplaint)
    complaint.id = uuid4()
    complaint.company_id = company_id
    complaint.entity_id = entity_id
    complaint.submitted_by_id = portal_user_id
    complaint.document_id = None
    complaint.invoice_tracking_id = None
    complaint.reference_number = "RK-20260202-A1B2C3D4"
    complaint.complaint_type = ComplaintType.INVOICE_ERROR.value
    complaint.subject = "Falscher Betrag auf Rechnung"
    complaint.description = "Die Rechnung RE-2026-00123 weist einen falschen Gesamtbetrag auf."
    complaint.status = ComplaintStatus.NEW
    complaint.priority = "normal"
    complaint.assigned_to_id = None
    complaint.internal_notes = None
    complaint.resolution = None
    complaint.metadata = {}
    complaint.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    complaint.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
    complaint.first_response_at = None
    complaint.resolved_at = None
    complaint.closed_at = None
    return complaint


# ========================= PortalMessage Fixtures =========================


@pytest.fixture
def sample_message_inbound(company_id: UUID, entity_id: UUID, portal_user_id: UUID) -> PortalMessage:
    """
    Provide inbound PortalMessage (from customer).
    """
    message = MagicMock(spec=PortalMessage)
    message.id = uuid4()
    message.company_id = company_id
    message.entity_id = entity_id
    message.complaint_id = None
    message.portal_user_id = portal_user_id
    message.internal_user_id = None
    message.direction = MessageDirection.INBOUND.value
    message.subject = "Frage zur Rechnung"
    message.content = "Ich habe eine Frage zu meiner letzten Rechnung."
    message.attachments = []
    message.is_read = True
    message.read_at = datetime.now(timezone.utc) - timedelta(hours=1)
    message.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    return message


@pytest.fixture
def sample_message_outbound(company_id: UUID, entity_id: UUID) -> PortalMessage:
    """
    Provide outbound PortalMessage (to customer).
    """
    message = MagicMock(spec=PortalMessage)
    message.id = uuid4()
    message.company_id = company_id
    message.entity_id = entity_id
    message.complaint_id = None
    message.portal_user_id = None
    message.internal_user_id = uuid4()
    message.direction = MessageDirection.OUTBOUND.value
    message.subject = "Re: Frage zur Rechnung"
    message.content = "Vielen Dank fuer Ihre Anfrage. Hier sind die Details..."
    message.attachments = []
    message.is_read = False
    message.read_at = None
    message.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    return message


# ========================= PortalDocument Fixtures =========================


@pytest.fixture
def sample_portal_document(company_id: UUID, entity_id: UUID, portal_user_id: UUID) -> PortalDocument:
    """
    Provide sample PortalDocument.
    """
    doc = MagicMock(spec=PortalDocument)
    doc.id = uuid4()
    doc.company_id = company_id
    doc.entity_id = entity_id
    doc.uploaded_by_id = portal_user_id
    doc.complaint_id = None
    doc.message_id = None
    doc.document_id = None
    doc.original_filename = "rechnung_scan.pdf"
    doc.file_size = 245000
    doc.mime_type = "application/pdf"
    doc.storage_path = f"{company_id}/{entity_id}/20260202_120000_rechnung_scan.pdf"
    doc.description = "Scan unserer Originalrechnung"
    doc.document_type = "invoice"
    doc.processing_status = "pending"
    doc.processed_at = None
    doc.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    return doc


# ========================= PortalPaymentConfirmation Fixtures =========================


@pytest.fixture
def sample_payment_confirmation(
    company_id: UUID, entity_id: UUID, portal_user_id: UUID, invoice_id: UUID
) -> PortalPaymentConfirmation:
    """
    Provide sample PortalPaymentConfirmation.
    """
    conf = MagicMock(spec=PortalPaymentConfirmation)
    conf.id = uuid4()
    conf.company_id = company_id
    conf.entity_id = entity_id
    conf.portal_user_id = portal_user_id
    conf.invoice_tracking_id = invoice_id
    conf.payment_date = datetime.now(timezone.utc) - timedelta(days=1)
    conf.payment_amount = "1190.00"
    conf.payment_reference = "RE-2026-00123"
    conf.payment_method = "bank_transfer"
    conf.attachment_ids = []
    conf.status = "pending"
    conf.verified_at = None
    conf.verified_by_id = None
    conf.rejection_reason = None
    conf.notes = "Zahlung erfolgte per Ueberweisung"
    conf.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    return conf


# ========================= Helper Functions =========================


def generate_invoices(
    entity_id: UUID,
    company_id: UUID,
    count: int = 5,
    status: str = "open"
) -> List[MagicMock]:
    """
    Generate list of mock invoices for testing.
    """
    invoices = []
    for i in range(count):
        inv = MagicMock()
        inv.id = uuid4()
        inv.entity_id = entity_id
        inv.company_id = company_id
        inv.document_id = uuid4()
        inv.invoice_number = f"RE-2026-{i+100:05d}"
        inv.invoice_date = date.today() - timedelta(days=i * 7)
        inv.due_date = date.today() + timedelta(days=30 - i * 7)
        inv.gross_amount = Decimal(str(100 * (i + 1)))
        inv.net_amount = Decimal(str(round(100 * (i + 1) / 1.19, 2)))
        inv.currency = "EUR"
        inv.status = status
        inv.dunning_level = 0
        inv.paid_amount = Decimal("0.00")
        inv.outstanding_amount = inv.gross_amount
        inv.skonto_percentage = Decimal("2.0") if i % 2 == 0 else None
        inv.skonto_deadline = date.today() + timedelta(days=5) if i % 2 == 0 else None
        inv.skonto_amount = Decimal(str(round(float(inv.gross_amount) * 0.02, 2))) if i % 2 == 0 else None
        inv.partial_payments = []
        inv.document = MagicMock()
        invoices.append(inv)
    return invoices


def generate_complaints(
    entity_id: UUID,
    company_id: UUID,
    portal_user_id: UUID,
    count: int = 3
) -> List[MagicMock]:
    """
    Generate list of mock complaints for testing.
    """
    types = list(ComplaintType)
    statuses = [ComplaintStatus.NEW, ComplaintStatus.IN_REVIEW, ComplaintStatus.RESOLVED]

    complaints = []
    for i in range(count):
        comp = MagicMock(spec=PortalComplaint)
        comp.id = uuid4()
        comp.company_id = company_id
        comp.entity_id = entity_id
        comp.submitted_by_id = portal_user_id
        comp.reference_number = f"RK-20260202-{secrets.token_hex(4).upper()}"
        comp.complaint_type = types[i % len(types)].value
        comp.subject = f"Reklamation {i + 1}"
        comp.description = f"Beschreibung der Reklamation {i + 1}"
        comp.status = statuses[i % len(statuses)]
        comp.priority = "normal"
        comp.resolution = "Geloest" if comp.status == ComplaintStatus.RESOLVED else None
        comp.metadata = {}
        comp.created_at = datetime.now(timezone.utc) - timedelta(days=i)
        comp.updated_at = datetime.now(timezone.utc) - timedelta(hours=i)
        comp.first_response_at = datetime.now(timezone.utc) - timedelta(hours=i + 12) if i > 0 else None
        comp.resolved_at = datetime.now(timezone.utc) - timedelta(hours=1) if comp.status == ComplaintStatus.RESOLVED else None
        comp.closed_at = None
        complaints.append(comp)
    return complaints


def generate_messages(
    entity_id: UUID,
    company_id: UUID,
    portal_user_id: UUID,
    count: int = 5
) -> List[MagicMock]:
    """
    Generate list of mock messages for testing.
    """
    messages = []
    for i in range(count):
        msg = MagicMock(spec=PortalMessage)
        msg.id = uuid4()
        msg.company_id = company_id
        msg.entity_id = entity_id
        msg.complaint_id = None
        msg.portal_user_id = portal_user_id if i % 2 == 0 else None
        msg.internal_user_id = uuid4() if i % 2 == 1 else None
        msg.direction = MessageDirection.INBOUND.value if i % 2 == 0 else MessageDirection.OUTBOUND.value
        msg.subject = f"Nachricht {i + 1}"
        msg.content = f"Inhalt der Nachricht {i + 1}"
        msg.attachments = []
        msg.is_read = i < 3
        msg.read_at = datetime.now(timezone.utc) - timedelta(hours=i) if msg.is_read else None
        msg.created_at = datetime.now(timezone.utc) - timedelta(hours=count - i)
        messages.append(msg)
    return messages
