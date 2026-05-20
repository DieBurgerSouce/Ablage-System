"""Create zm_submissions table directly."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import os

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS zm_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period VARCHAR(7) NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMP WITH TIME ZONE,
    submitted_by UUID REFERENCES users(id),
    bzst_reference VARCHAR(100),
    bzst_response_code VARCHAR(20),
    bzst_response_message TEXT,
    total_amount NUMERIC(15, 2),
    record_count INTEGER,
    triangular_count INTEGER,
    countries_involved JSONB,
    deadline DATE NOT NULL,
    is_late BOOLEAN DEFAULT FALSE,
    original_submission_id UUID REFERENCES zm_submissions(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_zm_submission_period UNIQUE (user_id, company_id, period)
)
"""

async def create_table():
    db_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://ablage:ablage@postgres:5432/ablage')
    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        await conn.execute(text(SQL_CREATE_TABLE))
        print('Table created!')

        await conn.execute(text('CREATE INDEX IF NOT EXISTS ix_zm_submissions_period ON zm_submissions(period)'))
        await conn.execute(text('CREATE INDEX IF NOT EXISTS ix_zm_submissions_status ON zm_submissions(status)'))
        await conn.execute(text('CREATE INDEX IF NOT EXISTS ix_zm_submissions_deadline ON zm_submissions(deadline, is_late)'))
        await conn.execute(text('CREATE INDEX IF NOT EXISTS ix_zm_submissions_user_id ON zm_submissions(user_id)'))
        print('Indexes created!')

if __name__ == '__main__':
    asyncio.run(create_table())
    print('Done!')
