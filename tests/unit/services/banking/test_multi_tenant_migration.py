# -*- coding: utf-8 -*-
"""Tests for Banking Multi-Tenant Migration (user_id → company_id).

Validates that all banking services correctly use company_id for multi-tenant isolation.

Migration: 232_banking_multi_tenant.py
"""

import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta
from uuid import uuid4, UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BankAccount,
    BankImport,
    PaymentBatch,
    PaymentOrder,
    DunningRecord,
    Company,
    User,
)
from app.services.banking.account_service import AccountService
from app.services.banking.import_service import ImportService
from app.services.banking.payment_service import PaymentService
from app.services.banking.dunning_service import DunningService
from app.services.banking.transaction_service import TransactionService


class TestBankingMultiTenantMigration:
    """Test suite for banking multi-tenant migration."""

    @pytest.fixture
    async def company_a(self, db: AsyncSession) -> Company:
        """Create test company A."""
        company = Company(
            id=uuid4(),
            name="Company A GmbH",
            created_at=datetime.utcnow(),
        )
        db.add(company)
        await db.commit()
        await db.refresh(company)
        return company

    @pytest.fixture
    async def company_b(self, db: AsyncSession) -> Company:
        """Create test company B."""
        company = Company(
            id=uuid4(),
            name="Company B AG",
            created_at=datetime.utcnow(),
        )
        db.add(company)
        await db.commit()
        await db.refresh(company)
        return company

    @pytest.fixture
    async def bank_account_company_a(
        self, db: AsyncSession, company_a: Company
    ) -> BankAccount:
        """Create bank account for company A."""
        account = BankAccount(
            id=uuid4(),
            company_id=company_a.id,
            account_name="Company A Account",
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            bank_name="Commerzbank",
            account_holder="Company A GmbH",
            account_type="checking",
            currency="EUR",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return account

    @pytest.fixture
    async def bank_account_company_b(
        self, db: AsyncSession, company_b: Company
    ) -> BankAccount:
        """Create bank account for company B."""
        account = BankAccount(
            id=uuid4(),
            company_id=company_b.id,
            account_name="Company B Account",
            iban="DE89370400440532013001",
            bic="COBADEFFXXX",
            bank_name="Commerzbank",
            account_holder="Company B AG",
            account_type="checking",
            currency="EUR",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return account

    # =========================================================================
    # Test 1-5: Bank Account Service Multi-Tenancy
    # =========================================================================

    async def test_bank_account_service_uses_company_id(
        self, db: AsyncSession, company_a: Company
    ):
        """Test 1: AccountService creates accounts with company_id."""
        from app.services.banking.models import BankAccountCreate

        service = AccountService()
        # W1-Fix: gueltige IBAN (DE89...3002 hatte eine falsche Pruefziffer -
        # der Service validiert die IBAN, die Fixtures umgehen die Validierung)
        data = BankAccountCreate(
            account_name="Test Account",
            iban="DE02120300000000202051",
            bic="COBADEFFXXX",
            bank_name="Test Bank",
            account_holder="Test Holder",
            currency="EUR",
        )

        result = await service.create_account(db, company_a.id, data)

        # Verify company_id is set
        assert result.company_id == company_a.id

        # Verify in database
        stmt = select(BankAccount).where(BankAccount.id == result.id)
        db_account = (await db.execute(stmt)).scalar_one()
        assert db_account.company_id == company_a.id

    async def test_bank_account_isolation_between_companies(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
        bank_account_company_a: BankAccount,
        bank_account_company_b: BankAccount,
    ):
        """Test 2: Bank accounts are isolated by company_id."""
        service = AccountService()

        # Company A should only see its own accounts
        accounts_a = await service.get_accounts(db, company_a.id)
        account_ids_a = [acc.id for acc in accounts_a]
        assert bank_account_company_a.id in account_ids_a
        assert bank_account_company_b.id not in account_ids_a

        # Company B should only see its own accounts
        accounts_b = await service.get_accounts(db, company_b.id)
        account_ids_b = [acc.id for acc in accounts_b]
        assert bank_account_company_b.id in account_ids_b
        assert bank_account_company_a.id not in account_ids_b

    async def test_bank_account_cannot_access_other_company_account(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
        bank_account_company_b: BankAccount,
    ):
        """Test 3: Company A cannot access Company B's bank account."""
        service = AccountService()

        # Try to get Company B's account using Company A's ID
        result = await service.get_account(
            db, company_a.id, bank_account_company_b.id
        )

        # Should return None (access denied)
        assert result is None

    async def test_bank_account_update_respects_company_id(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
        bank_account_company_a: BankAccount,
    ):
        """Test 4: Bank account updates respect company_id."""
        from app.services.banking.models import BankAccountUpdate

        service = AccountService()
        update_data = BankAccountUpdate(account_name="Updated Name")

        # Company A can update its own account
        result = await service.update_account(
            db, company_a.id, bank_account_company_a.id, update_data
        )
        assert result is not None
        assert result.account_name == "Updated Name"

        # Company B cannot update Company A's account
        result = await service.update_account(
            db, company_b.id, bank_account_company_a.id, update_data
        )
        assert result is None

    async def test_bank_account_delete_respects_company_id(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
        bank_account_company_a: BankAccount,
    ):
        """Test 5: Bank account deletion respects company_id."""
        service = AccountService()

        # Company B cannot delete Company A's account
        success = await service.delete_account(
            db, company_b.id, bank_account_company_a.id
        )
        assert success is False

        # Company A can delete its own account
        success = await service.delete_account(
            db, company_a.id, bank_account_company_a.id
        )
        assert success is True

    # =========================================================================
    # Test 6-10: Bank Import Service Multi-Tenancy
    # =========================================================================

    async def test_bank_import_service_uses_company_id(
        self,
        db: AsyncSession,
        company_a: Company,
        bank_account_company_a: BankAccount,
    ):
        """Test 6: ImportService creates imports with company_id."""
        service = ImportService()

        csv_content = """Date;Amount;Purpose
2024-01-01;100.00;Test"""

        result, tx_ids = await service.import_file(
            db=db,
            company_id=company_a.id,
            content=csv_content,
            filename="test.csv",
            bank_account_id=bank_account_company_a.id,
        )

        # Verify company_id is set
        assert result.company_id == company_a.id

        # Verify in database
        stmt = select(BankImport).where(BankImport.id == result.id)
        db_import = (await db.execute(stmt)).scalar_one()
        assert db_import.company_id == company_a.id

    async def test_bank_import_history_isolation(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
        bank_account_company_a: BankAccount,
        bank_account_company_b: BankAccount,
    ):
        """Test 7: Import history is isolated by company_id."""
        service = ImportService()

        # Create import for Company A
        csv_a = "Date;Amount;Purpose\n2024-01-01;100.00;Test A"
        await service.import_file(
            db, company_a.id, csv_a, "a.csv", bank_account_company_a.id
        )

        # Create import for Company B
        csv_b = "Date;Amount;Purpose\n2024-01-01;200.00;Test B"
        await service.import_file(
            db, company_b.id, csv_b, "b.csv", bank_account_company_b.id
        )

        # Company A should only see its own imports
        history_a = await service.get_import_history(db, company_a.id)
        assert len(history_a) == 1
        assert history_a[0].company_id == company_a.id

        # Company B should only see its own imports
        history_b = await service.get_import_history(db, company_b.id)
        assert len(history_b) == 1
        assert history_b[0].company_id == company_b.id

    # =========================================================================
    # Test 8-12: Payment Service Multi-Tenancy
    # =========================================================================

    async def test_payment_service_uses_company_id(
        self,
        db: AsyncSession,
        company_a: Company,
        bank_account_company_a: BankAccount,
    ):
        """Test 8: PaymentService creates payments with company_id."""
        from app.services.banking.models import PaymentOrderCreate, PaymentType

        service = PaymentService()
        payment_data = PaymentOrderCreate(
            bank_account_id=bank_account_company_a.id,
            payment_type=PaymentType.TRANSFER,
            beneficiary_name="Test Beneficiary",
            beneficiary_iban="DE02120300000000202051",
            amount=Decimal("100.00"),
            reference="Test Payment",
            currency="EUR",
        )

        result = await service.create_payment(
            db, company_a.id, bank_account_company_a.id, payment_data
        )

        # Verify die Zahlung ist company_a zugeordnet. PaymentOrder hat KEINE
        # bank_account-Relationship (nur bank_account_id) -> direkt auf der
        # company_id-Spalte pruefen (das ist das eigentliche Scope-Feld).
        stmt = select(PaymentOrder).where(PaymentOrder.id == result.id)
        db_payment = (await db.execute(stmt)).scalar_one()
        assert db_payment.company_id == company_a.id

    async def test_payment_list_isolation(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
        bank_account_company_a: BankAccount,
        bank_account_company_b: BankAccount,
    ):
        """Test 9: Payment lists are isolated by company_id."""
        from app.services.banking.models import PaymentOrderCreate, PaymentType

        service = PaymentService()

        # Create payment for Company A
        payment_a = PaymentOrderCreate(
            bank_account_id=bank_account_company_a.id,
            payment_type=PaymentType.TRANSFER,
            beneficiary_name="A Beneficiary",
            beneficiary_iban="DE02120300000000202051",
            amount=Decimal("100.00"),
            reference="Payment A",
            currency="EUR",
        )
        await service.create_payment(
            db, company_a.id, bank_account_company_a.id, payment_a
        )

        # Create payment for Company B
        payment_b = PaymentOrderCreate(
            bank_account_id=bank_account_company_b.id,
            payment_type=PaymentType.TRANSFER,
            beneficiary_name="B Beneficiary",
            beneficiary_iban="DE75512108001245126199",
            amount=Decimal("200.00"),
            reference="Payment B",
            currency="EUR",
        )
        await service.create_payment(
            db, company_b.id, bank_account_company_b.id, payment_b
        )

        # Company A should only see its payments
        payments_a, count_a = await service.list_payments(db, company_a.id)
        assert count_a == 1

        # Company B should only see its payments
        payments_b, count_b = await service.list_payments(db, company_b.id)
        assert count_b == 1

    async def test_skonto_opportunities_isolation(
        self,
        db: AsyncSession,
        company_a: Company,
        company_b: Company,
    ):
        """Test 9b: Skonto-Chancen sind company-scoped (Mig 269).

        Firma A hat eine Skonto-faehige Rechnung. Firma B darf diese NICHT
        sehen (Mandanten-Isolation), Firma A schon.
        """
        from app.db.models import Document

        skonto_date = date.today() + timedelta(days=5)

        # Skonto-faehige Rechnung fuer Firma A. owner_id bleibt NULL (FK auf
        # users.id); der Scope laeuft ausschliesslich ueber company_id, ein
        # Besitzer ist fuer die Sichtbarkeit nicht mehr relevant.
        doc_a = Document(
            id=uuid4(),
            company_id=company_a.id,
            document_type="invoice",
            filename="skonto_a.pdf",
            original_filename="skonto_a.pdf",
            file_path="/test/skonto_a.pdf",
            extracted_data={
                "invoice_number": "RE-A-001",
                "sender": {"name": "Lieferant A"},
                "amounts": {"gross": 1000.00},
                "payment_terms": {
                    "skonto": {
                        "date": skonto_date.isoformat(),
                        "percent": 2.0,
                    }
                },
            },
            created_at=datetime.utcnow(),
        )
        db.add(doc_a)
        await db.commit()

        service = PaymentService()

        # Firma A sieht ihre Skonto-Chance
        opps_a = await service.get_skonto_opportunities(
            db, company_a.id, days_ahead=14
        )
        assert len(opps_a) == 1
        assert opps_a[0]["invoice_number"] == "RE-A-001"
        assert opps_a[0]["potential_savings"] == 20.0

        # Firma B darf die Skonto-Chance von Firma A NICHT sehen
        opps_b = await service.get_skonto_opportunities(
            db, company_b.id, days_ahead=14
        )
        assert len(opps_b) == 0

    # =========================================================================
    # Test 10-15: Dunning Service Multi-Tenancy
    # =========================================================================

    async def test_dunning_service_uses_company_id(
        self, db: AsyncSession, company_a: Company
    ):
        """Test 10: DunningService creates dunning records with company_id."""
        from app.db.models import Document
        from app.services.banking.models import DunningLevel

        # Create test document (invoice).
        # W1-Fix: original_filename ist NOT NULL; owner_id ist FK auf users.id
        # (frueher wurde faelschlich die Company-ID gesetzt -> FK-Verletzung).
        doc = Document(
            id=uuid4(),
            company_id=company_a.id,
            document_type="invoice",
            filename="test_invoice.pdf",
            original_filename="test_invoice.pdf",
            file_path="/test/invoice.pdf",
            extracted_data={
                "total_amount": "500.00",
                "due_date": "2024-01-01",
                "payment_status": "unpaid",
            },
            created_at=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()

        service = DunningService()
        result = await service.create_dunning(
            db, company_a.id, doc.id, DunningLevel.FIRST_REMINDER
        )

        # Verify company_id is set
        stmt = select(DunningRecord).where(DunningRecord.id == result.id)
        db_dunning = (await db.execute(stmt)).scalar_one()
        assert db_dunning.company_id == company_a.id

    async def test_dunning_list_isolation(
        self, db: AsyncSession, company_a: Company, company_b: Company
    ):
        """Test 11: Dunning lists are isolated by company_id."""
        from app.db.models import Document
        from app.services.banking.models import DunningLevel

        # Create dunning for Company A (W1-Fix: original_filename NOT NULL,
        # company_id statt faelschlichem owner_id=Company-UUID)
        doc_a = Document(
            id=uuid4(),
            company_id=company_a.id,
            document_type="invoice",
            filename="invoice_a.pdf",
            original_filename="invoice_a.pdf",
            file_path="/test/a.pdf",
            extracted_data={
                "total_amount": "500.00",
                "due_date": "2024-01-01",
            },
            created_at=datetime.utcnow(),
        )
        db.add(doc_a)

        # Create dunning for Company B
        doc_b = Document(
            id=uuid4(),
            company_id=company_b.id,
            document_type="invoice",
            filename="invoice_b.pdf",
            original_filename="invoice_b.pdf",
            file_path="/test/b.pdf",
            extracted_data={
                "total_amount": "600.00",
                "due_date": "2024-01-01",
            },
            created_at=datetime.utcnow(),
        )
        db.add(doc_b)
        await db.commit()

        service = DunningService()
        await service.create_dunning(
            db, company_a.id, doc_a.id, DunningLevel.FIRST_REMINDER
        )
        await service.create_dunning(
            db, company_b.id, doc_b.id, DunningLevel.FIRST_REMINDER
        )

        # Company A should only see its dunnings
        dunnings_a, count_a = await service.list_dunnings(db, company_a.id)
        assert count_a == 1

        # Company B should only see its dunnings
        dunnings_b, count_b = await service.list_dunnings(db, company_b.id)
        assert count_b == 1

    # =========================================================================
    # Test 12-15: Migration Backfill Validation
    # =========================================================================

    async def test_migration_backfill_bank_accounts(
        self, db: AsyncSession, company_a: Company
    ):
        """Test 12: Verify migration backfilled company_id from user.company_id."""
        # This test assumes the migration has run
        # Check that all bank_accounts have non-null company_id
        stmt = select(BankAccount).where(BankAccount.company_id.is_(None))
        result = await db.execute(stmt)
        null_company_accounts = result.scalars().all()

        assert (
            len(null_company_accounts) == 0
        ), "All bank accounts should have company_id after migration"

    async def test_migration_backfill_bank_imports(self, db: AsyncSession):
        """Test 13: Verify migration backfilled company_id in bank_imports."""
        stmt = select(BankImport).where(BankImport.company_id.is_(None))
        result = await db.execute(stmt)
        null_company_imports = result.scalars().all()

        assert (
            len(null_company_imports) == 0
        ), "All bank imports should have company_id after migration"

    async def test_migration_backfill_payment_batches(self, db: AsyncSession):
        """Test 14: Verify migration backfilled company_id in payment_batches."""
        stmt = select(PaymentBatch).where(PaymentBatch.company_id.is_(None))
        result = await db.execute(stmt)
        null_company_batches = result.scalars().all()

        assert (
            len(null_company_batches) == 0
        ), "All payment batches should have company_id after migration"

    async def test_migration_backfill_dunning_records(self, db: AsyncSession):
        """Test 15: Verify migration backfilled company_id in dunning_records."""
        stmt = select(DunningRecord).where(DunningRecord.company_id.is_(None))
        result = await db.execute(stmt)
        null_company_dunnings = result.scalars().all()

        assert (
            len(null_company_dunnings) == 0
        ), "All dunning records should have company_id after migration"

    # =========================================================================
    # Test 16-17: Foreign Key Constraints
    # =========================================================================

    async def test_foreign_key_cascade_delete(
        self, db: AsyncSession, company_a: Company, bank_account_company_a: BankAccount
    ):
        """Test 16: Verify CASCADE delete on company removal."""
        account_id = bank_account_company_a.id

        # Delete company
        await db.delete(company_a)
        await db.commit()

        # Bank account should be deleted via CASCADE
        stmt = select(BankAccount).where(BankAccount.id == account_id)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()

        assert account is None, "Bank account should be deleted with company (CASCADE)"

    async def test_composite_index_performance(
        self, db: AsyncSession, company_a: Company
    ):
        """Test 17: Verify composite indexes exist for performance."""
        # This test verifies that queries using company_id + is_active
        # and company_id + status can use composite indexes

        # Test bank_accounts composite index
        from sqlalchemy import text

        result = await db.execute(
            text(
                """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'bank_accounts'
            AND indexdef LIKE '%company_id%is_active%'
        """
            )
        )
        indexes = result.fetchall()

        assert (
            len(indexes) > 0
        ), "Composite index on (company_id, is_active) should exist"

