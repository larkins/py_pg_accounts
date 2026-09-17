"""System-wide settings stored in Postgres.

Why this exists (2026-09-17, open-source prep):

    Constants like the business name ("Peristyle"), default super-fund
    ABN/USI ("AustralianSuper"), and similar were hardcoded in source.
    For a multi-tenant / multi-fund deployment, those need to come from
    configuration rather than source. This module provides a tiny key-value
    table for runtime-tunable settings.

Lookup precedence (highest priority first):

    1. Explicit override passed to `get_setting()` (caller-provided value)
    2. PostgreSQL `system_settings` table (seeded by `seed_defaults()` on
       app boot; can be edited via `set_setting()` from anywhere — API,
       admin UI, cron)
    3. Environment variable `SETTING_<KEY>` (uppercased, dot → underscore)
    4. Hard-coded default passed as `default=` to `get_setting()`

Typical usage:

    from app.models.system_setting import get_setting, set_setting

    # In a route handler:
    fund_name = get_setting('DEFAULT_FUND_NAME')
    fund_abn = get_setting('DEFAULT_FUND_ABN')

    # In a startup hook (seed_defaults runs on app boot if the table is empty):
    set_setting('BUSINESS_NAME', 'Peristyle')

The table is intentionally simple — no audit trail, no versioning, no
encryption. If you need those, use a separate config store; this is for
runtime-tunable business constants.

Schema:
    key    VARCHAR(100) PRIMARY KEY
    value  TEXT NOT NULL
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""

import os

from sqlalchemy import event

from . import db


class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=db.func.now(),
        onupdate=db.func.now(),
    )

    def __repr__(self):
        return f'<SystemSetting {self.key}={self.value!r}>'


# ---------------------------------------------------------------------------
# Default values seeded into the table on first boot (when the table is empty).
# These match the values that were previously hardcoded in source. Override
# via SETTING_* env vars or via `set_setting()` at runtime.
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    # Business identity (appears on payslips, invoices, SAFF files).
    'BUSINESS_NAME': 'Peristyle',

    # Default super fund (used as a fallback when an employee record
    # doesn't specify their own fund name). The fund ABN/USI are PUBLIC
    # data — published by the ATO Fund USI/SPIN Lookup.
    'DEFAULT_FUND_NAME': 'AustralianSuper',
    'DEFAULT_FUND_ABN': '65714394898',
    'DEFAULT_FUND_USI': 'STA0100AU',
}


def _env_key(setting_key):
    """Convert a settings key to its env var form.

    Examples:
        BUSINESS_NAME      -> SETTING_BUSINESS_NAME
        DEFAULT_FUND_ABN   -> SETTING_DEFAULT_FUND_ABN
    """
    return 'SETTING_' + setting_key.upper().replace('.', '_').replace('-', '_')


def get_setting(key, default=None):
    """Look up a setting. See module docstring for precedence.

    Returns the explicit override if provided, otherwise checks the
    database, then env var, then the hard-coded default.
    """
    # 1. DB
    row = SystemSetting.query.filter_by(key=key).first()
    if row is not None:
        return row.value
    # 2. Env var
    env_val = os.environ.get(_env_key(key))
    if env_val is not None and env_val != '':
        return env_val
    # 3. Hard-coded default
    return default


def set_setting(key, value):
    """Set a setting (insert or update). Commits immediately.

    Use `get_setting()` with the same key to read it back.
    """
    row = SystemSetting.query.filter_by(key=key).first()
    if row is None:
        row = SystemSetting(key=key, value=str(value))
        db.session.add(row)
    else:
        row.value = str(value)
    db.session.commit()


def seed_defaults(app=None):
    """Insert any keys from DEFAULT_SETTINGS that don't already exist.

    Safe to call multiple times — it only inserts missing keys, never
    overwrites existing values. Idempotent across app restarts.

    Called from app/__init__.py after db.create_all() so a fresh install
    picks up sensible defaults without manual setup.
    """
    for key, default in DEFAULT_SETTINGS.items():
        if SystemSetting.query.filter_by(key=key).first() is None:
            db.session.add(SystemSetting(key=key, value=default))
    db.session.commit()
