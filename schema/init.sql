-- PostgreSQL Schema for Accounting System
-- Run as: psql -d py_pg_accounts -f schema/init.sql

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
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
    address TEXT,
    contact_email VARCHAR(255),
    contact_number VARCHAR(50),
    logo_path VARCHAR(500),
    bank_name VARCHAR(255),
    account_name VARCHAR(255),
    account_number VARCHAR(50),
    bsb VARCHAR(20),
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

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    address TEXT,
    contact_email VARCHAR(255),
    abn VARCHAR(20),
    contact_number VARCHAR(50),
    gst BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);

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

-- Comments for documentation
COMMENT ON TABLE users IS 'User accounts with authentication and API access. email_verified required before API key usage.';
COMMENT ON TABLE account_categories IS 'Chart of accounts categories for classification';
COMMENT ON TABLE expenses IS 'Expense records with GST tracking';
COMMENT ON TABLE invoices IS 'Invoice records with GST tracking';
COMMENT ON TABLE activity_logs IS 'Audit trail of all database modifications';
COMMENT ON TABLE ocr_queue IS 'Queue for OCR processing of receipt images via vision model';
COMMENT ON TABLE employees IS 'Employee master record. PII columns (tfn, bank_bsb, bank_account_number) are encrypted at rest via app/shared/pii.py (Fernet, key in .env as PAYROLL_PII_KEY). KMS upgrade is Phase 5.';
COMMENT ON TABLE pay_events IS 'One row per payslip issued. Headline amounts are source of truth; pay_event_lines is the itemised view.';
COMMENT ON TABLE pay_event_lines IS 'Itemised breakdown of a pay event (earnings, tax, deductions, allowances, employer contributions).';
COMMENT ON TABLE payslip_deliveries IS 'Audit trail of every payslip email sent. One row per recipient per send.';
COMMENT ON TABLE super_payments IS 'Superannuation remittances. One row per actual fund payment, covering one or more pay_events.';
