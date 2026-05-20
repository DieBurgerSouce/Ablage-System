-- Create zm_submissions table for tracking ZM filing status
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
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_zm_submissions_period ON zm_submissions(period);
CREATE INDEX IF NOT EXISTS ix_zm_submissions_status ON zm_submissions(status);
CREATE INDEX IF NOT EXISTS ix_zm_submissions_deadline ON zm_submissions(deadline, is_late);
CREATE INDEX IF NOT EXISTS ix_zm_submissions_user_id ON zm_submissions(user_id);
