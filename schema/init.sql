-- PostgreSQL Schema for Accounting System
-- Run as: psql -d py_pg_accounts -f schema/init.sql
--
-- This file is the authoritative schema. New tables are normally created
-- automatically by db.create_all() on app startup (see app/models/*), but
-- every committed model MUST also be reflected here so fresh installs from
-- scratch have the full schema. Last synced with live DB on 2026-09-07
-- (added bas_lodgements from 01cc090 + bank_transactions from 74eef7b +
-- invoice_reminders + pending_payment_reconciliations from 08 Sep 2026).

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table (the business owner; one per business)
-- 2026-09-17: same address refactor as customers — structured fields only
-- (legacy free-text `address` column dropped same day). Note: `country` is
-- the user's locale (2-letter ISO code: 'AU', 'US', etc.); `address_country`
-- is the address's country name ('Australia', 'United States', etc.).
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    country VARCHAR(50) NOT NULL DEFAULT 'AU',
    api_key VARCHAR(64) UNIQUE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_token VARCHAR(64),
    business_name VARCHAR(255),
    abn VARCHAR(20),
    -- Structured address fields (preferred for writes & integrations)
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    postcode VARCHAR(20),
    address_country VARCHAR(100) NOT NULL DEFAULT 'Australia',
    contact_email VARCHAR(255),
    contact_number VARCHAR(50),
    logo_path VARCHAR(500),
    bank_name VARCHAR(255),
    account_name VARCHAR(255),
    account_number VARCHAR(500),
    bsb VARCHAR(500),
    payment_terms INTEGER NOT NULL DEFAULT 14,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_verification_token ON users(verification_token);

-- Account Categories table
CREATE TABLE IF NOT EXISTS account_categories (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Expenses table
CREATE TABLE IF NOT EXISTS expenses (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_category_id VARCHAR(36) REFERENCES account_categories(id) ON DELETE SET NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'browser',
    vendor_name VARCHAR(255) NOT NULL,
    description TEXT,
    currency VARCHAR(3) NOT NULL DEFAULT 'AUD',
    original_currency_amount NUMERIC(12, 2),
    exchange_rate NUMERIC(10, 6),
    ex_gst_amount NUMERIC(12, 2) NOT NULL,
    gst_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    gst_type NUMERIC(3, 1) NOT NULL DEFAULT 0,
    total_amount NUMERIC(12, 2) NOT NULL,
    expense_date DATE NOT NULL,
    attachment_path VARCHAR(500),
    requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at);
CREATE INDEX IF NOT EXISTS idx_expenses_requires_review ON expenses(requires_review);

-- Customers table (defined BEFORE invoices because invoices.customer_id FKs to it)
-- 2026-09-17: address split into structured columns (line1, line2, city, state,
-- postcode, country). 2026-09-17 (same day, second pass): the legacy
-- free-text `address` TEXT column was DROPPED entirely to avoid drift
-- between denormalised blob and structured columns. State is constrained to
-- AU state abbreviations at the API layer (no DB CHECK so we don't block
-- non-AU customers from countries we don't currently support).
CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    postcode VARCHAR(20),
    country VARCHAR(100) NOT NULL DEFAULT 'Australia',
    contact_email VARCHAR(255),
    abn VARCHAR(20),
    contact_number VARCHAR(50),
    gst BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotent migration for existing installs (added 2026-09-17).
ALTER TABLE customers ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(255);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS state VARCHAR(50);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS postcode VARCHAR(20);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS country VARCHAR(100) NOT NULL DEFAULT 'Australia';
-- Employees DOB column (added 2026-09-17 alongside SAFF work).
ALTER TABLE employees ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR(500);
-- Address + sex + phone (added 2026-09-17 for SAFF exports).
ALTER TABLE employees ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(255);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS state VARCHAR(50);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS postcode VARCHAR(20);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS sex VARCHAR(10);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS phone VARCHAR(30);
-- Legacy column dropped (added 2026-09-17 second pass). IF EXISTS so this
-- is safe to run on already-clean installs.
ALTER TABLE customers DROP COLUMN IF EXISTS address;

CREATE INDEX IF NOT EXISTS idx_customers_user_id ON customers(user_id);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_state ON customers(state);
CREATE INDEX IF NOT EXISTS idx_customers_postcode ON customers(postcode);

-- Users address migration (same shape as customers above). Added 2026-09-17.
ALTER TABLE users ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS state VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS postcode VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS address_country VARCHAR(100) NOT NULL DEFAULT 'Australia';
-- Legacy column dropped (added 2026-09-17 second pass).
ALTER TABLE users DROP COLUMN IF EXISTS address;

-- Invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_category_id VARCHAR(36) REFERENCES account_categories(id) ON DELETE SET NULL,
    customer_id VARCHAR(36) REFERENCES customers(id) ON DELETE RESTRICT,
    client_name VARCHAR(255) NOT NULL,
    description TEXT,
    ex_gst_amount NUMERIC(12, 2) NOT NULL,
    gst_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    gst_type NUMERIC(3, 1) NOT NULL DEFAULT 0,
    total_amount NUMERIC(12, 2) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE,
    attachment_path VARCHAR(500),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    payment_date DATE,
    amount_paid NUMERIC(12, 2),
    sent_at TIMESTAMPTZ,
    confirmed_received_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at);
CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);

-- Activity Logs table
CREATE TABLE IF NOT EXISTS activity_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    table_name VARCHAR(50) NOT NULL,
    record_id VARCHAR(36) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON activity_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_logs_table_name ON activity_logs(table_name);
CREATE INDEX IF NOT EXISTS idx_activity_logs_record_id ON activity_logs(record_id);

-- OCR Queue table
CREATE TABLE IF NOT EXISTS ocr_queue (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    expense_id VARCHAR(36) NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    image_path VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    extracted_data JSONB,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ocr_queue_expense_id ON ocr_queue(expense_id);
CREATE INDEX IF NOT EXISTS idx_ocr_queue_status ON ocr_queue(status);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_expenses_updated_at ON expenses;
CREATE TRIGGER update_expenses_updated_at
    BEFORE UPDATE ON expenses
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_invoices_updated_at ON invoices;
CREATE TRIGGER update_invoices_updated_at
    BEFORE UPDATE ON invoices
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Payroll expansion (2026-08-27) — see payroll_expansion.md
-- Five new tables, idempotent. PII columns (tfn, bank_bsb, bank_account_number)
-- are VARCHAR(500) to hold Fernet ciphertext (Phase 1a). KMS upgrade is Phase 5.
-- ============================================================================

CREATE TABLE IF NOT EXISTS employees (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    legal_name VARCHAR(255) NOT NULL,
    preferred_name VARCHAR(255),
    position VARCHAR(255),
    email_work VARCHAR(255),
    email_personal VARCHAR(255),
    tfn VARCHAR(500),
    -- Date of birth (2026-09-17): encrypted at rest like the other PII
    -- columns. Stored as ciphertext of an ISO date string ('YYYY-MM-DD').
    date_of_birth VARCHAR(500),
    start_date DATE,
    end_date DATE,
    employment_status VARCHAR(20) NOT NULL DEFAULT 'active',
    pay_frequency VARCHAR(20) NOT NULL DEFAULT 'weekly',
    default_gross_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    super_fund_name VARCHAR(255),
    super_fund_member_no VARCHAR(50),
    super_rate_pct NUMERIC(5, 2) NOT NULL DEFAULT 12.00,
    bank_account_name VARCHAR(255),
    bank_bsb VARCHAR(500),
    bank_account_number VARCHAR(500),
    bank_reference_prefix VARCHAR(10),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employees_user_id ON employees(user_id);
CREATE INDEX IF NOT EXISTS idx_employees_user_status ON employees(user_id, employment_status);
CREATE INDEX IF NOT EXISTS idx_employees_legal_name ON employees(legal_name);

CREATE TABLE IF NOT EXISTS pay_events (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    payment_date DATE NOT NULL,
    pay_period_start DATE NOT NULL,
    pay_period_end DATE NOT NULL,
    pay_frequency VARCHAR(20) NOT NULL,
    position_snapshot VARCHAR(255),
    gross_amount NUMERIC(12, 2) NOT NULL,
    payg_tax_amount NUMERIC(12, 2) NOT NULL,
    net_amount NUMERIC(12, 2) NOT NULL,
    super_ote_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    super_payable_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    super_paid_amount NUMERIC(12, 2),
    super_paid_date DATE,
    bank_reference VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    notes TEXT,
    payslip_pdf_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_pay_period_order CHECK (pay_period_end >= pay_period_start),
    CONSTRAINT chk_amounts_nonneg CHECK (
        gross_amount >= 0 AND payg_tax_amount >= 0 AND net_amount >= 0
        AND super_ote_amount >= 0
    ),
    CONSTRAINT uq_pay_event_bank_ref UNIQUE (user_id, employee_id, bank_reference)
);

CREATE INDEX IF NOT EXISTS idx_pay_events_user_date ON pay_events(user_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_pay_events_user_emp_date
    ON pay_events(user_id, employee_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_pay_events_user_status ON pay_events(user_id, status);

CREATE TABLE IF NOT EXISTS pay_event_lines (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    pay_event_id VARCHAR(36) NOT NULL REFERENCES pay_events(id) ON DELETE CASCADE,
    line_type VARCHAR(30) NOT NULL,
    description VARCHAR(255),
    quantity NUMERIC(10, 2),
    rate NUMERIC(10, 2),
    amount NUMERIC(12, 2) NOT NULL,
    is_taxable BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pay_event_lines_event
    ON pay_event_lines(pay_event_id, sort_order);

CREATE TABLE IF NOT EXISTS payslip_deliveries (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    pay_event_id VARCHAR(36) NOT NULL REFERENCES pay_events(id) ON DELETE CASCADE,
    recipient_email VARCHAR(255) NOT NULL,
    recipient_kind VARCHAR(20) NOT NULL DEFAULT 'work',
    sent_from VARCHAR(255) NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    subject VARCHAR(500),
    attachment_count INTEGER NOT NULL DEFAULT 0,
    attachment_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'queued',
    delivery_id VARCHAR(64),
    error_message TEXT,
    mail_api_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payslip_deliveries_event ON payslip_deliveries(pay_event_id);
CREATE INDEX IF NOT EXISTS idx_payslip_deliveries_recipient ON payslip_deliveries(recipient_email);
CREATE INDEX IF NOT EXISTS idx_payslip_deliveries_sent_at ON payslip_deliveries(sent_at);
CREATE INDEX IF NOT EXISTS idx_payslip_deliveries_status ON payslip_deliveries(delivery_status);

CREATE TABLE IF NOT EXISTS super_payments (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    employee_id VARCHAR(36) NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    remittance_date DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    pay_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    fund_name_snapshot VARCHAR(255),
    fund_member_snapshot VARCHAR(50),
    payment_reference VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_super_payments_user_emp_date
    ON super_payments(user_id, employee_id, remittance_date);

-- Bas lodgements table (added 2026-08-31)
--
-- Records the FACT of lodgement with the ATO: receipt ID, timestamp, account
-- name, final settled amount, and any manual adjustments (prior-period
-- credits, deferred BAS, label adjustments, instalment interest). Separate
-- from /api/reports/quarterly-bas (which returns COMPUTED net GST) because
-- the ATO settlement often differs due to prior-period credits, label
-- adjustments, etc.
--
-- Australian FY: Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun. Per-user +
-- per-(financial_year, quarter) uniqueness prevents duplicate lodgement
-- entries for the same period.
CREATE TABLE IF NOT EXISTS bas_lodgements (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    financial_year VARCHAR(9) NOT NULL,                 -- e.g. 'FY2025/26'
    quarter INTEGER NOT NULL,                          -- 1..4 (Australian FY)
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    ato_receipt_id VARCHAR(64),
    ato_account_name VARCHAR(255),
    lodged_at TIMESTAMPTZ NOT NULL,
    lodgement_method VARCHAR(20) NOT NULL DEFAULT 'online',  -- 'online' | 'paper' | 'agent'
    gst_collected NUMERIC(12, 2),                      -- BAS label 1A
    gst_paid NUMERIC(12, 2),                           -- BAS label 1B
    computed_net_gst NUMERIC(12, 2),                   -- 1A - 1B before ATO adjustments
    final_amount NUMERIC(12, 2) NOT NULL,              -- actually settled
    final_amount_type VARCHAR(10) NOT NULL,            -- 'credit' | 'owe' | 'zero'
    prior_credit_carried NUMERIC(12, 2) DEFAULT 0,
    other_adjustments NUMERIC(12, 2) DEFAULT 0,
    adjustments_note TEXT,
    notes TEXT,
    screenshot_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bas_lodgements_user_id
    ON bas_lodgements(user_id);
-- One lodgement per (user, FY, quarter). Two lodgements for the same period
-- would be a recording error; surface it via 409 instead of silently allowing.
CREATE UNIQUE INDEX IF NOT EXISTS idx_bas_lodgements_user_fy_quarter
    ON bas_lodgements(user_id, financial_year, quarter);

-- Bank transactions table (added 2026-09-07)
--
-- Records payments received into the business bank account with full
-- bank-side provenance: transaction ID, payer-supplied reference, method
-- (Osko/BPay/direct credit/etc.), payer name + account, amount, settlement
-- date. Optional FK back to invoice so each bank txn can be linked to the
-- invoice it pays (or left null for non-invoice receipts like interest,
-- refunds, owner contributions).
--
-- Why this exists: the Invoice model has no field for bank-side provenance,
-- so before this table the bank transaction ID + reference string had
-- nowhere to go. Without them we can't reconcile the bank statement
-- against invoices, and the BAS report can't show real settlement dates.
CREATE TABLE IF NOT EXISTS bank_transactions (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invoice_id VARCHAR(36) REFERENCES invoices(id) ON DELETE SET NULL,
    transaction_id VARCHAR(64),                        -- bank-side txn ID, e.g. CTBAAUSNXXXN...
    reference VARCHAR(255),                            -- payer-supplied ref, e.g. 'INV-XXX - SOFTWARE'
    method VARCHAR(32),                                -- 'osko' | 'bpay' | 'direct_credit' | 'cheque' | 'cash' | 'other'
    payer_name VARCHAR(255),
    payer_account VARCHAR(64),
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'AUD',
    transaction_date DATE NOT NULL,                    -- date the bank shows it as processed (BAS date)
    settled_at TIMESTAMPTZ,
    notes TEXT,
    raw_source VARCHAR(32) NOT NULL DEFAULT 'manual',  -- 'manual' | 'bank_feed_csv' | 'screenshot_ocr'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_bank_transactions_user_id
    ON bank_transactions(user_id);
CREATE INDEX IF NOT EXISTS ix_bank_transactions_invoice_id
    ON bank_transactions(invoice_id);
CREATE INDEX IF NOT EXISTS ix_bank_transactions_transaction_date
    ON bank_transactions(transaction_date);

-- Invoice reminders / statement-of-account log (added 2026-09-08).
-- Tracks every outbound (or inbound) communication tied to a specific
-- invoice, used for aged-receivable chasing and escalation history.
-- A single statement-of-account email that covers multiple outstanding
-- invoices produces one row per invoice, all sharing the same email_id.
CREATE TABLE IF NOT EXISTS invoice_reminders (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    invoice_id VARCHAR(36) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,

    reminder_type VARCHAR(20) NOT NULL,                 -- 'statement' | 'chase' | 'dunning' | 'payment_reminder' | 'thank_you' | 'phone_call' | 'in_person' | 'other'
    channel       VARCHAR(20) NOT NULL DEFAULT 'email', -- 'email' | 'phone' | 'sms' | 'in_person' | 'mail' | 'other'
    direction     VARCHAR(10) NOT NULL DEFAULT 'outbound', -- 'outbound' | 'inbound'

    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    sent_by      VARCHAR(255),                          -- email/name of sender
    sent_by_kind VARCHAR(20) NOT NULL DEFAULT 'human',  -- 'human' | 'evie' | 'cron' | 'system' | 'unknown'

    email_id            VARCHAR(64),                    -- mail server message id; groups rows from one email event
    pdf_attachment_path VARCHAR(500),

    recipients   TEXT,
    subject      VARCHAR(500),
    body_excerpt TEXT,
    notes        TEXT,

    response_received_at TIMESTAMPTZ,
    payment_received_at  TIMESTAMPTZ,
    days_overdue_at_send INTEGER,                       -- snapshot of overdue state when reminder was sent

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_invoice_reminders_user_id      ON invoice_reminders(user_id);
CREATE INDEX IF NOT EXISTS ix_invoice_reminders_customer_id  ON invoice_reminders(customer_id);
CREATE INDEX IF NOT EXISTS ix_invoice_reminders_invoice_id   ON invoice_reminders(invoice_id);
CREATE INDEX IF NOT EXISTS ix_invoice_reminders_sent_at      ON invoice_reminders(sent_at);
CREATE INDEX IF NOT EXISTS ix_invoice_reminders_email_id     ON invoice_reminders(email_id);
CREATE INDEX IF NOT EXISTS ix_invoice_reminders_user_invoice_sent
    ON invoice_reminders(user_id, invoice_id, sent_at DESC);

-- Pending payment reconciliations (added 2026-09-08).
-- Records every remittance advice (e.g. Xero "Payment has been made" email)
-- received for a customer. Rows sit in `pending` status until a human
-- confirms the money actually landed in the bank account — remittance
-- advice is the PAYER's claim, not proof of payment.
CREATE TABLE IF NOT EXISTS pending_payment_reconciliations (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_id VARCHAR(36) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    invoice_id VARCHAR(36) REFERENCES invoices(id) ON DELETE SET NULL,  -- nullable if reference doesn't match any invoice

    source_email_id   VARCHAR(64),
    source_sender     VARCHAR(255),
    source_subject    VARCHAR(500),
    pdf_attachment_path VARCHAR(500),

    payer_name VARCHAR(255),
    payer_abn  VARCHAR(20),
    payment_date DATE,
    sent_date    DATE,
    reference_text VARCHAR(500),           -- "5C1A4C6F - SOFTWARE"
    invoice_ref_token VARCHAR(8),          -- "5C1A4C6F" — first 8 chars of invoice UUID, uppercased
    amount NUMERIC(12, 2),
    amount_currency VARCHAR(3) NOT NULL DEFAULT 'AUD',

    status VARCHAR(20) NOT NULL DEFAULT 'pending',   -- 'pending' | 'confirmed' | 'rejected' | 'stale'

    reconciled_at TIMESTAMPTZ,
    reconciled_by VARCHAR(255),                      -- email or 'evie'
    bank_reference VARCHAR(255),
    bank_screenshot_path VARCHAR(500),
    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pending_recon_user_id        ON pending_payment_reconciliations(user_id);
CREATE INDEX IF NOT EXISTS ix_pending_recon_customer_id    ON pending_payment_reconciliations(customer_id);
CREATE INDEX IF NOT EXISTS ix_pending_recon_invoice_id     ON pending_payment_reconciliations(invoice_id);
CREATE INDEX IF NOT EXISTS ix_pending_recon_ref_token      ON pending_payment_reconciliations(invoice_ref_token);
CREATE INDEX IF NOT EXISTS ix_pending_recon_status         ON pending_payment_reconciliations(status);
CREATE INDEX IF NOT EXISTS ix_pending_recon_source_email   ON pending_payment_reconciliations(source_email_id);
CREATE INDEX IF NOT EXISTS ix_pending_recon_user_status    ON pending_payment_reconciliations(user_id, status, created_at DESC);

-- Reuse the existing update_updated_at_column() function
DROP TRIGGER IF EXISTS update_employees_updated_at ON employees;
CREATE TRIGGER update_employees_updated_at
    BEFORE UPDATE ON employees
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_pay_events_updated_at ON pay_events;
CREATE TRIGGER update_pay_events_updated_at
    BEFORE UPDATE ON pay_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_super_payments_updated_at ON super_payments;
CREATE TRIGGER update_super_payments_updated_at
    BEFORE UPDATE ON super_payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_bas_lodgements_updated_at ON bas_lodgements;
CREATE TRIGGER update_bas_lodgements_updated_at
    BEFORE UPDATE ON bas_lodgements
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_invoice_reminders_updated_at ON invoice_reminders;
CREATE TRIGGER update_invoice_reminders_updated_at
    BEFORE UPDATE ON invoice_reminders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_pending_payment_reconciliations_updated_at ON pending_payment_reconciliations;
CREATE TRIGGER update_pending_payment_reconciliations_updated_at
    BEFORE UPDATE ON pending_payment_reconciliations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- bank_transactions has no updated_at column (audit-only, immutable row),
-- so no trigger needed.

-- Comments for documentation
COMMENT ON TABLE users IS 'User accounts with authentication and API access. email_verified required before API key usage.';
COMMENT ON TABLE account_categories IS 'Chart of accounts categories for classification';
COMMENT ON TABLE expenses IS 'Expense records with GST tracking';
COMMENT ON TABLE invoices IS 'Invoice records with GST tracking';
COMMENT ON TABLE activity_logs IS 'Audit trail of all database modifications';
COMMENT ON TABLE ocr_queue IS 'Queue for OCR processing of receipt images via vision model';
COMMENT ON TABLE employees IS 'Employee master record. PII columns (tfn, bank_bsb, bank_account_number, date_of_birth) are encrypted at rest via app/shared/pii.py (Fernet, key in .env as PAYROLL_PII_KEY). KMS upgrade is Phase 5.';
COMMENT ON TABLE pay_events IS 'One row per payslip issued. Headline amounts are source of truth; pay_event_lines is the itemised view.';
COMMENT ON TABLE pay_event_lines IS 'Itemised breakdown of a pay event (earnings, tax, deductions, allowances, employer contributions).';
COMMENT ON TABLE payslip_deliveries IS 'Audit trail of every payslip email sent. One row per recipient per send.';
COMMENT ON TABLE super_payments IS 'Superannuation remittances. One row per actual fund payment, covering one or more pay_events.';
COMMENT ON TABLE bas_lodgements IS 'BAS (Business Activity Statement) lodgements with the ATO. Records the FACT of lodgement (receipt ID, settled amount, manual adjustments), separate from the COMPUTED figures in /api/reports/quarterly-bas.';
COMMENT ON TABLE bank_transactions IS 'Bank-side provenance for received payments: transaction ID, payer-supplied reference, method (Osko/BPay/etc.), amount, settlement date. Optional FK to invoice. Immutable row (no updated_at) — corrections are delete + re-record.';
COMMENT ON TABLE invoice_reminders IS 'Append-only log of every statement/chase/communication tied to an invoice. Used to track aged-receivable chasing and reconstruct escalation history. A single statement-of-account email that covers N invoices produces N rows sharing the same email_id.';
COMMENT ON TABLE pending_payment_reconciliations IS 'Records every remittance advice (e.g. Xero "Payment has been made" email) received for a customer. Rows stay in `pending` status until a human confirms the bank account shows the money actually landed — remittance advice is the PAYER''s claim, not proof of payment.';


-- ============================================================================
-- System settings (added 2026-09-17 for open-source release)
-- ----------------------------------------------------------------------------
-- Key/value store for app-wide runtime-tunable constants (business name,
-- default super fund identifiers, etc.). Replaces what used to be hardcoded
-- in source. Seeded with DEFAULT_SETTINGS via seed_defaults() on app boot.
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_settings (
    key        VARCHAR(100) PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE system_settings IS 'Key/value store for runtime-tunable app-wide constants. Seeded with defaults on boot; updatable via API. Lookup precedence: explicit override > DB row > SETTING_<KEY> env var > caller default.';

CREATE TRIGGER update_system_settings_updated_at
    BEFORE UPDATE ON system_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===================== payee_directory =====================
-- Added 2026-09-21 — org-scoped bank destinations for outbound payments
-- (super clearing houses, ATO, suppliers, etc.). Bank details are
-- Fernet-encrypted at rest (F-05 pattern; mirrored from employees.bank_*).
-- See app/models/payee_directory.py and schema/migrate_payee_directory.sql.
CREATE TABLE IF NOT EXISTS payee_directory (
    id              VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id         VARCHAR(36) NOT NULL REFERENCES users(id),

    -- Human-facing
    label           VARCHAR(64) NOT NULL,
    use_case        VARCHAR(32),                      -- 'super_clearing_house' | 'ato' | 'wages' | 'supplier' | 'other'
    account_name    VARCHAR(255) NOT NULL,

    -- F-05 encrypted ciphertext columns (use Payee.bsb_plain /
    -- Payee.account_number_plain accessors to read; *_masked via to_dict()).
    bsb             VARCHAR(500),
    account_number  VARCHAR(500),

    -- Lifecycle
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    notes           TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payee_directory_user
    ON payee_directory(user_id);

CREATE INDEX IF NOT EXISTS idx_payee_directory_user_use_case
    ON payee_directory(user_id, use_case)
    WHERE is_active = TRUE;

COMMENT ON TABLE payee_directory IS
    'Org-scoped bank destinations for outbound payments (super clearing houses, ATO, suppliers, etc.). bsb/account_number stored Fernet-encrypted (F-05).';
COMMENT ON COLUMN payee_directory.bsb IS 'Fernet ciphertext. Decrypt via Payee.bsb_plain.';
COMMENT ON COLUMN payee_directory.account_number IS 'Fernet ciphertext. Decrypt via Payee.account_number_plain.';

CREATE TRIGGER update_payee_directory_updated_at
    BEFORE UPDATE ON payee_directory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===================== users.de_user_id =====================
-- Added 2026-09-21 — NAB-issued 6-digit Direct Entry Credit User ID,
-- embedded in ABA file header positions 57-62. Stored Fernet-encrypted
-- (F-05 pattern; mirrors users.bsb / users.account_number).
-- Use User.de_user_id_plain to read.
-- See schema/migrate_user_de_user_id.sql for the existing-DB migration.
ALTER TABLE users ADD COLUMN IF NOT EXISTS de_user_id VARCHAR(500);

COMMENT ON COLUMN users.de_user_id IS
    'Fernet ciphertext. NAB-issued 6-digit Direct Entry Credit User ID, embedded in ABA file header positions 57-62. Decrypt via User.de_user_id_plain. NULL until user supplies the real ID from their NAB Connect onboarding email.';
