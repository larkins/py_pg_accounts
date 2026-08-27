"""Employee master record.

PII columns (tfn, bank_bsb, bank_account_number) are stored as Fernet
ciphertext (see app/shared/pii.py). Use the `*_plain` accessors to read the
real value; the default `to_dict()` returns masked values.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.hybrid import hybrid_property

from . import db, get_utc_now
from app.shared import pii


class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    legal_name = db.Column(db.String(255), nullable=False)
    preferred_name = db.Column(db.String(255), nullable=True)
    position = db.Column(db.String(255), nullable=True)
    email_work = db.Column(db.String(255), nullable=True)
    email_personal = db.Column(db.String(255), nullable=True)

    # Stored as Fernet ciphertext (VARCHAR(500) holds the base64 blob).
    # Read via the *_plain accessors; write via the *_plain setters.
    _tfn = db.Column('tfn', db.String(500), nullable=True)
    _bank_bsb = db.Column('bank_bsb', db.String(500), nullable=True)
    _bank_account_number = db.Column('bank_account_number', db.String(500), nullable=True)

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    employment_status = db.Column(db.String(20), nullable=False, default='active')
    pay_frequency = db.Column(db.String(20), nullable=False, default='weekly')
    default_gross_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    super_fund_name = db.Column(db.String(255), nullable=True)
    super_fund_member_no = db.Column(db.String(50), nullable=True)
    super_rate_pct = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal('12.00'))

    bank_account_name = db.Column(db.String(255), nullable=True)
    bank_reference_prefix = db.Column(db.String(10), nullable=True)

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)

    # ------------------------------------------------------------------
    # PII accessors
    # ------------------------------------------------------------------
    # `tfn`, `bank_bsb`, `bank_account_number` are stored encrypted. We hide
    # the underlying column behind `_<name>` attributes and expose:
    #   - `<name>_plain`        : plaintext (str or None)
    #   - `<name>_masked`       : display-safe masked form
    #   - `<name>` (property)   : masked form (safe default for to_dict)
    # Plain setters go through encrypt_pii() — callers that want to assign
    # raw ciphertext should not exist. Use tfn_plain = '...' in code, not
    # `employee._tfn = '...'`.
    # ------------------------------------------------------------------

    # --- TFN ---
    @hybrid_property
    def tfn_plain(self):
        return pii.decrypt_pii(self._tfn)

    @tfn_plain.setter
    def tfn_plain(self, value):
        self._tfn = pii.encrypt_pii(value)

    @hybrid_property
    def tfn_masked(self):
        return pii.mask_tfn(self.tfn_plain)

    @hybrid_property
    def tfn(self):
        return self.tfn_masked

    # --- bank_bsb ---
    @hybrid_property
    def bank_bsb_plain(self):
        return pii.decrypt_pii(self._bank_bsb)

    @bank_bsb_plain.setter
    def bank_bsb_plain(self, value):
        self._bank_bsb = pii.encrypt_pii(value)

    @hybrid_property
    def bank_bsb_masked(self):
        return pii.mask_bsb(self.bank_bsb_plain)

    @hybrid_property
    def bank_bsb(self):
        return self.bank_bsb_masked

    # --- bank_account_number ---
    @hybrid_property
    def bank_account_number_plain(self):
        return pii.decrypt_pii(self._bank_account_number)

    @bank_account_number_plain.setter
    def bank_account_number_plain(self, value):
        self._bank_account_number = pii.encrypt_pii(value)

    @hybrid_property
    def bank_account_number_masked(self):
        return pii.mask_account(self.bank_account_number_plain)

    @hybrid_property
    def bank_account_number(self):
        return self.bank_account_number_masked

    # ------------------------------------------------------------------
    # to_dict — masked PII by default. Call `to_dict(include_pii_plain=True)`
    # if you really need the plaintext (PDF generator, encrypted at rest so
    # decrypt is just a fetch + a logged server-side op).
    # ------------------------------------------------------------------
    def to_dict(self, include_pii_plain=False):
        out = {
            'id': self.id,
            'user_id': self.user_id,
            'legal_name': self.legal_name,
            'preferred_name': self.preferred_name,
            'position': self.position,
            'email_work': self.email_work,
            'email_personal': self.email_personal,
            'tfn': self.tfn_masked,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'employment_status': self.employment_status,
            'pay_frequency': self.pay_frequency,
            'default_gross_amount': str(self.default_gross_amount) if self.default_gross_amount is not None else None,
            'super_fund_name': self.super_fund_name,
            'super_fund_member_no': self.super_fund_member_no,
            'super_rate_pct': str(self.super_rate_pct),
            'bank_account_name': self.bank_account_name,
            'bank_bsb': self.bank_bsb_masked,
            'bank_account_number': self.bank_account_number_masked,
            'bank_reference_prefix': self.bank_reference_prefix,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_pii_plain:
            out['tfn_plain'] = self.tfn_plain
            out['bank_bsb_plain'] = self.bank_bsb_plain
            out['bank_account_number_plain'] = self.bank_account_number_plain
        return out
