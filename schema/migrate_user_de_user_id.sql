-- =============================================================================
-- Migration: Add users.de_user_id (F-05 encrypted, holds the NAB-issued
-- Direct Entry Credit User ID for ABA file generation).
-- =============================================================================
--
-- Date: 2026-09-21
--
-- The DE User ID is a 6-digit number assigned by NAB/ACPA and embedded in
-- the Cemtex ABA file header at positions 57-62. Until now the placeholder
-- '301500' was hard-coded in app/shared/aba.py:build_header_record, which
-- NAB rejects with error 317651 ("The 'From account' details must be
-- entered"). The real ID comes from NAB Connect onboarding email and must
-- be supplied by the user.
--
-- Storing it as Fernet ciphertext (F-05 pattern, mirroring bsb/account_number
-- on this same table). Use User.de_user_id_plain to read.
--
-- Run as DB owner:
--   psql -U <owner> -d py_pg_accounts -f schema/migrate_user_de_user_id.sql
--
-- Idempotent (uses IF NOT EXISTS where possible).
-- =============================================================================

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS de_user_id VARCHAR(500);

COMMENT ON COLUMN users.de_user_id IS
    'Fernet ciphertext. NAB-issued 6-digit Direct Entry Credit User ID, embedded in ABA file header positions 57-62. Decrypt via User.de_user_id_plain. NULL until user supplies the real ID from their NAB Connect onboarding email.';

COMMIT;
