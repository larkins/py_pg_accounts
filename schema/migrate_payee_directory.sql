-- =============================================================================
-- Migration: Add payee_directory table (third-party bank destinations)
-- =============================================================================
--
-- Date: 2026-09-21
--
-- Adds an org-scoped (per-user) directory of frequently-used bank
-- destinations for outbound payments. Until now, bank details for
-- non-employee payees (e.g. super clearing houses, ATO, suppliers)
-- had no home in the schema: they had to be supplied ad-hoc each time
-- a payment file was generated.
--
-- The Australian Super clearing house Wrkr Pay is the first entry —
-- peristyle.ai's chosen clearing house for all employee super
-- contributions, regardless of the underlying fund.
--
-- PII columns (bsb, account_number) are stored as Fernet ciphertext
-- (F-05 pattern, mirroring employees.bank_bsb). Use the model's
-- `*_plain` accessors to read; the default `to_dict()` returns masked
-- values.
--
-- Run as DB owner:
--   psql -U <owner> -d py_pg_accounts -f schema/migrate_payee_directory.sql
--
-- Idempotent (CREATE TABLE IF NOT EXISTS).
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS payee_directory (
    id              VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id         VARCHAR(36) NOT NULL REFERENCES users(id),

    -- Human-facing
    label           VARCHAR(64) NOT NULL,            -- e.g. 'Wrkr Super (clearing house)'
    use_case        VARCHAR(32),                     -- 'super_clearing_house' | 'ato' | 'wages' | 'other'

    -- Bank destination (F-05 encrypted)
    account_name    VARCHAR(255) NOT NULL,           -- plaintext (not actually secret)
    bsb             VARCHAR(500),                    -- Fernet ciphertext; use bsb_plain
    account_number  VARCHAR(500),                    -- Fernet ciphertext; use account_number_plain

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
COMMENT ON COLUMN payee_directory.bsb IS
    'Fernet ciphertext. Decrypt via Payee.bsb_plain.';
COMMENT ON COLUMN payee_directory.account_number IS
    'Fernet ciphertext. Decrypt via Payee.account_number_plain.';

COMMIT;
