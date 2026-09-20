-- Migration: Add user_id to customers table (F-10 user-scope customer records)
-- Date: 2026-09-20
--
-- Customers were previously shared across all users (IDOR vulnerability).
-- This migration adds a user_id column, backfills existing rows to the
-- first user (single-user deployment migration path), then enforces
-- NOT NULL and adds an index.
--
-- Run as: psql -d py_pg_accounts -f schema/migrate_customer_user_id.sql

BEGIN;

-- Step 1: Add the column (nullable initially so we can backfill)
ALTER TABLE customers ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id);

-- Step 2: Backfill existing rows to the first user (single-user deployment)
UPDATE customers
SET user_id = (SELECT id FROM users ORDER BY created_at ASC LIMIT 1)
WHERE user_id IS NULL;

-- Step 3: Enforce NOT NULL now that all rows are populated
ALTER TABLE customers ALTER COLUMN user_id SET NOT NULL;

-- Step 4: Add index for query performance
CREATE INDEX IF NOT EXISTS idx_customers_user_id ON customers(user_id);

COMMIT;
