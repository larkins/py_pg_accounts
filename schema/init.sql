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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at);

-- Invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_category_id VARCHAR(36) REFERENCES account_categories(id) ON DELETE SET NULL,
    client_name VARCHAR(255) NOT NULL,
    description TEXT,
    ex_gst_amount NUMERIC(12, 2) NOT NULL,
    gst_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    gst_type NUMERIC(3, 1) NOT NULL DEFAULT 0,
    total_amount NUMERIC(12, 2) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE,
    attachment_path VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at);

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

-- Comments for documentation
COMMENT ON TABLE users IS 'User accounts with authentication and API access. email_verified required before API key usage.';
COMMENT ON TABLE account_categories IS 'Chart of accounts categories for classification';
COMMENT ON TABLE expenses IS 'Expense records with GST tracking';
COMMENT ON TABLE invoices IS 'Invoice records with GST tracking';
COMMENT ON TABLE activity_logs IS 'Audit trail of all database modifications';
