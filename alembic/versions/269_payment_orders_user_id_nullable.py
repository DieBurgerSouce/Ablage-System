"""payment_orders/payment_batches.user_id DROP NOT NULL (PaymentService company-scope).

PaymentService wird von user- auf company-scoped umgestellt. Migration 232 hatte das
Banking company-scoped gemacht, Migration 268 aber nur ``bank_accounts``/``bank_imports``/
``dunning_records`` auf ``user_id`` nullable gesetzt - ``payment_orders`` und
``payment_batches`` blieben uebrig (genau die Luecke, die die strict-xfail-Tests
``test_payment_service_uses_company_id`` / ``test_payment_list_isolation`` festhalten):
company-scoped angelegte Konten haben ``user_id=NULL``, der einzige Scope-Filter war aber
``BankAccount.user_id == user_id`` -> "Bankkonto nicht gefunden" bzw. NotNullViolation beim
Anlegen der Zahlung.

``company_id`` existiert bereits ``NOT NULL`` + indexiert (Migration 232) -> kein Backfill,
keine neue Spalte/FK noetig. ``user_id`` bleibt als reiner Audit-/Ersteller-Kontext erhalten,
nur eben nullable.

Idempotent (``DROP NOT NULL`` ist no-op, wenn bereits nullable), additiv. Downgrade laesst
die Nullability bewusst stehen (kein Datenverlust - company-scoped Zeilen koennen
``user_id=NULL`` haben; ein ``SET NOT NULL`` wuerde scheitern). Analog zu Migration 268.

Revision ID: 269
Revises: 268
Create Date: 2026-06-20
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "269"
down_revision = "268"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # payment_orders: create_payment legt company-scoped Zahlungen ohne user_id an.
    bind.execute(sa.text(
        "ALTER TABLE payment_orders ALTER COLUMN user_id DROP NOT NULL"
    ))
    # payment_batches: create_batch analog.
    bind.execute(sa.text(
        "ALTER TABLE payment_batches ALTER COLUMN user_id DROP NOT NULL"
    ))


def downgrade() -> None:
    # Nullability bleibt bewusst erhalten (kein Datenverlust; analog Migration 268).
    pass
