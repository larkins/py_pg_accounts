-- Migration: add invoice_cc_emails JSONB to customers
--
-- WHY: per-customer invoice Cc mailing list. Replaces hardcoded
-- CC_LIST constants scattered across send_enp_invoice.py,
-- send_polymedtech_invoice.py, and scripts/send_enp_invoice_to_customer.py.
-- Bug history: on 2026-09-28 the new send_enp_invoice_to_customer.py
-- omitted accountsos@enpfitouts.com.au because the recipient list wasn't
-- stored on the customer record — it was hardcoded in the script. Michael
-- asked for the mailing list to live on the customer so future scripts can
-- never silently regress.
--
-- Shape: JSONB array of lowercase email strings, e.g.:
--   ["phi@enpfitouts.com.au", "accountsos@enpfitouts.com.au", "mjlarkins@gmail.com"]
--
-- Validation lives in the API (see _validate_cc_emails helper), not in the
-- DB. NULL means "no CC list configured" (scripts fall back to []).
--
-- Idempotent: uses IF NOT EXISTS so safe to re-run.

BEGIN;

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS invoice_cc_emails JSONB;

-- Add a GIN index for cheap containment queries (e.g. "which customers get
-- CC'd to this address"). GIN supports the @> operator on JSONB arrays.
CREATE INDEX IF NOT EXISTS idx_customers_invoice_cc_emails
    ON customers USING GIN (invoice_cc_emails);

COMMENT ON COLUMN customers.invoice_cc_emails IS
    'Per-customer Cc mailing list for outgoing invoice emails (JSONB array of lowercase email strings). NULL/empty = no Cc recipients. Added 2026-09-28 to replace hardcoded CC_LIST constants in send_*_invoice.py scripts.';

COMMIT;
