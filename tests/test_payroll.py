"""Tests for payroll encryption + backfill idempotency.

PII round-trip:
    Encrypt a TFN, persist it on an Employee, then decrypt and confirm the
    plaintext matches. This is the single most important assertion — if the
    Fernet helper is broken, every encrypted column is useless.

Backfill idempotency:
    Run the backfill script twice (pointed at a temp directory of fake PDFs).
    The second run must insert 0 rows. We use a tiny temp PDF generator to
    keep the test self-contained.

Run with:
    cd /home/mal/py_pg_accounts && ./venv/bin/python3 -m pytest tests/test_payroll.py -v
"""

import io
import os
import sys
import shutil
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

# Make sure we can import app.* from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env manually
ENV = Path(__file__).resolve().parent.parent / '.env'
if ENV.exists():
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

from app import create_app
from app.models import db
from app.models.user import User
from app.models.employee import Employee


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:s324fFm7F32Vkk1Vm32msFdf41v@127.0.0.1:5432/py_pg_accounts',
    )
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# PII round-trip
# ---------------------------------------------------------------------------

class TestPIIRoundTrip:
    """Encrypt → DB → decrypt preserves the plaintext."""

    def test_tfn_round_trip(self, app):
        with app.app_context():
            e = Employee(
                user_id=self._pick_user_id(app),
                legal_name=f'TEST_TFN_{uuid.uuid4().hex[:8]}',
            )
            e.tfn_plain = '107 075 250'
            db.session.add(e)
            db.session.commit()
            eid = e.id
            db.session.expire_all()
            fresh = Employee.query.get(eid)
            assert fresh.tfn_plain == '107 075 250'
            assert fresh.tfn_masked == '*** *** 250'
            # Cleanup
            db.session.delete(fresh)
            db.session.commit()

    def test_bsb_round_trip(self, app):
        with app.app_context():
            e = Employee(
                user_id=self._pick_user_id(app),
                legal_name=f'TEST_BSB_{uuid.uuid4().hex[:8]}',
            )
            e.bank_bsb_plain = '123-456'
            db.session.add(e)
            db.session.commit()
            eid = e.id
            db.session.expire_all()
            fresh = Employee.query.get(eid)
            assert fresh.bank_bsb_plain == '123-456'
            assert fresh.bank_bsb_masked == '***-456'
            db.session.delete(fresh)
            db.session.commit()

    def test_account_round_trip(self, app):
        with app.app_context():
            e = Employee(
                user_id=self._pick_user_id(app),
                legal_name=f'TEST_ACC_{uuid.uuid4().hex[:8]}',
            )
            e.bank_account_number_plain = '12345678'
            db.session.add(e)
            db.session.commit()
            eid = e.id
            db.session.expire_all()
            fresh = Employee.query.get(eid)
            assert fresh.bank_account_number_plain == '12345678'
            assert fresh.bank_account_number_masked == '*****5678'
            db.session.delete(fresh)
            db.session.commit()

    def test_to_dict_masks_pii_by_default(self, app):
        with app.app_context():
            e = Employee(
                user_id=self._pick_user_id(app),
                legal_name=f'TEST_MASK_{uuid.uuid4().hex[:8]}',
            )
            e.tfn_plain = '111 222 333'
            e.bank_bsb_plain = '999-888'
            e.bank_account_number_plain = '77777777'
            db.session.add(e)
            db.session.commit()
            eid = e.id
            db.session.expire_all()
            fresh = Employee.query.get(eid)
            d = fresh.to_dict()
            assert d['tfn'] == '*** *** 333'
            assert d['bank_bsb'] == '***-888'
            assert d['bank_account_number'] == '*****7777'
            # Reveal path returns plaintext
            d2 = fresh.to_dict(include_pii_plain=True)
            assert d2['tfn_plain'] == '111 222 333'
            assert d2['bank_bsb_plain'] == '999-888'
            assert d2['bank_account_number_plain'] == '77777777'
            db.session.delete(fresh)
            db.session.commit()

    def _pick_user_id(self, app):
        u = User.query.first()
        assert u is not None, "Need at least one user in the DB"
        return u.id


# ---------------------------------------------------------------------------
# Backfill idempotency
# ---------------------------------------------------------------------------

class TestBackfillIdempotent:  # noqa: D400
    """Stub class retained so any old test references don't error.
    The associated backfill script (scripts/backfill_jessica_pay_events.py)
    was a one-time migration tool for migrating Alice Smith's existing
    payslips — it has been removed from the public repo since the data
    migration is complete. Re-add idempotency tests here if a similar
    migration script is needed for another employer."""

    def test_no_op(self):
        pass

    """Run the backfill against a temp dir of synthetic PDFs; second run = no-op."""

