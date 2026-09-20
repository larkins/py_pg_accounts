-- =============================================================================
-- Migration: Encrypt User bank details (F-05)
-- =============================================================================
--
-- Widens users.account_number and users.bsb from VARCHAR(50)/VARCHAR(20)
-- to VARCHAR(500) to hold Fernet ciphertext, then encrypts any existing
-- plaintext values.
--
-- Run as DB owner:
--   psql -U <owner> -d py_pg_accounts -f schema/migrate_encrypt_user_bank.sql
--
-- Prerequisites: PAYROLL_PII_KEY must be set in the environment for the
-- Python re-encryption step.
--
-- Idempotent: ALTER COLUMN is safe to re-run; the Python step skips rows
-- that are already Fernet ciphertext.
-- =============================================================================

-- Widen columns to hold Fernet ciphertext (~150-200 chars for short strings)
ALTER TABLE users ALTER COLUMN account_number TYPE VARCHAR(500);
ALTER TABLE users ALTER COLUMN bsb TYPE VARCHAR(500);

-- Encrypt existing plaintext values (run via Python):
--
--   python3 -c "
--   from app import create_app
--   from app.models import db
--   from app.models.user import User
--   from app.shared.pii import encrypt_pii
--   app = create_app()
--   with app.app_context():
--       for user in User.query.all():
--           changed = False
--           if user.account_number and not user.account_number.startswith('gAAAAA'):
--               user.account_number = encrypt_pii(user.account_number)
--               changed = True
--           if user.bsb and not user.bsb.startswith('gAAAAA'):
--               user.bsb = encrypt_pii(user.bsb)
--               changed = True
--           if changed:
--               print(f'Encrypted bank details for {user.email}')
--       db.session.commit()
--       print('Done')
--   "

COMMENT ON COLUMN users.account_number IS 'Fernet-encrypted bank account number. Decrypt via User.account_number_plain. Masked in to_dict().';
COMMENT ON COLUMN users.bsb IS 'Fernet-encrypted BSB. Decrypt via User.bsb_plain. Masked in to_dict().';
