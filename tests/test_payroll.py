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

class TestBackfillIdempotent:
    """Run the backfill against a temp dir of synthetic PDFs; second run = no-op."""

    def test_idempotent(self, app, tmp_path, monkeypatch):
        # Skip if pdftotext isn't installed
        import subprocess
        r = subprocess.run(['which', 'pdftotext'], capture_output=True, text=True)
        if r.returncode != 0:
            pytest.skip("pdftotext not installed")

        # Build a temp PDF dir
        pdf_dir = tmp_path / 'payslips'
        pdf_dir.mkdir()
        # Generate two synthetic payslip PDFs (filename must match the script's glob)
        for slug, payment_iso, period_iso, bank_ref, gross, payg, net, super_amt in [
            ('2026-09-02', '2026-09-02', '2026-08-25 to 2026-08-31', 'TEST_BACKFILL_001',
             '1900.00', '391.87', '1508.13', '228.00'),
            ('2026-09-09', '2026-09-09', '2026-09-01 to 2026-09-07', 'TEST_BACKFILL_002',
             '1900.00', '391.87', '1508.13', '228.00'),
        ]:
            pdf_dir.joinpath(f'payslip-jessica-paul-{slug}.pdf').write_bytes(
                _build_test_payslip(payment_iso, period_iso, bank_ref,
                                    gross, payg, net, super_amt)
            )

        # Override PDF_DIR + run the backfill via the script's main()
        monkeypatch.setattr(
            'scripts.backfill_jessica_pay_events.PDF_DIR', pdf_dir)
        # Adjust the script's _ensure_employee + _insert_pay_event so they
        # use a sandbox employee name (not "Jessica Paul" — that pollutes the
        # real Jessica row).
        from scripts import backfill_jessica_pay_events as bf
        monkeypatch.setitem(bf.EMPLOYEE, 'legal_name',
                            f'TEST_BF_{uuid.uuid4().hex[:8]}')

        with app.app_context():
            # First run
            rc = bf.main()
            assert rc == 0
            from app.models.pay_event import PayEvent
            n1 = PayEvent.query.filter(
                PayEvent.bank_reference.in_(['TEST_BACKFILL_001', 'TEST_BACKFILL_002'])
            ).count()
            assert n1 == 2, f"Expected 2 events after first run, got {n1}"

            # Second run — should be no-op
            rc = bf.main()
            assert rc == 0
            n2 = PayEvent.query.filter(
                PayEvent.bank_reference.in_(['TEST_BACKFILL_001', 'TEST_BACKFILL_002'])
            ).count()
            assert n2 == 2, f"Expected 2 events after second run (no-op), got {n2}"

            # Cleanup
            from app.models.pay_event_line import PayEventLine
            PayEventLine.query.filter(
                PayEventLine.pay_event_id.in_(
                    db.session.query(PayEvent.id).filter(
                        PayEvent.bank_reference.in_(['TEST_BACKFILL_001', 'TEST_BACKFILL_002'])
                    )
                )
            ).delete(synchronize_session=False)
            PayEvent.query.filter(
                PayEvent.bank_reference.in_(['TEST_BACKFILL_001', 'TEST_BACKFILL_002'])
            ).delete()
            Employee.query.filter(
                Employee.legal_name.like('TEST_BF_%')
            ).delete()
            db.session.commit()


def _build_test_payslip(payment_date, period, bank_ref, gross, payg, net, super_amt):
    """Generate a tiny PDF that pdftotext can parse back.

    Layout matches the real Jessica PDFs (Pay period / Payment date each on
    their own row, then a blank line, then the value) so the regex matchers
    in the backfill script work as they do against production PDFs.
    """
    # period is like "2026-08-25 to 2026-08-31" → convert to "25 Aug – 31 Aug 2026"
    from datetime import date as _date
    p_start, _, p_end = period.partition(' to ')
    ds = _date.fromisoformat(p_start)
    de = _date.fromisoformat(p_end)
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
              'Oct', 'Nov', 'Dec']
    period_rendered = (f'{ds.day} {months[ds.month - 1]} \u2013 '
                        f'{de.day} {months[de.month - 1]} {de.year}')
    payment_rendered = (f'{_date.fromisoformat(payment_date).day} '
                         f'{months[_date.fromisoformat(payment_date).month - 1]} '
                         f'{_date.fromisoformat(payment_date).year}')

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont('Helvetica-Bold', 18)
    c.drawString(2*cm, 27*cm, 'PAY SLIP')
    c.setFont('Helvetica', 10)
    c.drawString(2*cm, 26*cm, 'Pay period')
    c.drawString(2*cm, 25.5*cm, period_rendered)
    c.drawString(2*cm, 25*cm, 'Payment date')
    c.drawString(2*cm, 24.5*cm, payment_rendered)
    c.drawString(2*cm, 22*cm, 'Earnings & deductions Description Amount (AUD)')
    c.drawString(2*cm, 21.5*cm, f'Gross wages (weekly) ${gross}')
    c.drawString(2*cm, 21*cm, f'PAYG tax withheld ${payg}')
    c.drawString(2*cm, 20.5*cm, f'Net pay deposited ${net}')
    c.drawString(2*cm, 19*cm, 'Superannuation contribution @ 12% OTE')
    c.drawString(2*cm, 18.5*cm, f'${super_amt}')
    c.drawString(2*cm, 17*cm, 'Payment details')
    c.drawString(2*cm, 16.5*cm, 'Bank reference')
    c.drawString(2*cm, 16*cm, bank_ref)
    c.drawString(2*cm, 15.5*cm, 'Payment method Direct deposit')
    c.showPage()
    c.save()
    return buf.getvalue()