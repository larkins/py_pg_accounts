import uuid
from datetime import datetime, timezone
import secrets

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db, get_utc_now
from app.shared.pii import encrypt_pii, decrypt_pii, mask_bsb, mask_account


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    country = db.Column(db.String(50), nullable=False, default='AU')
    api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    verification_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    business_name = db.Column(db.String(255), nullable=True)
    abn = db.Column(db.String(20), nullable=True)
    # Structured address (the only address representation now). 2026-09-17
    # refactor removed the legacy free-text `address` TEXT column entirely
    # to avoid drift between denormalised blob and structured columns.
    # Note: `country` above is the user's locale (2-letter ISO: 'AU', 'US');
    # `address_country` below is the address's country name ('Australia').
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(50), nullable=True)
    postcode = db.Column(db.String(20), nullable=True)
    address_country = db.Column(db.String(100), nullable=False, default='Australia')
    contact_email = db.Column(db.String(255), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    logo_path = db.Column(db.String(500), nullable=True)
    bank_name = db.Column(db.String(255), nullable=True)
    account_name = db.Column(db.String(255), nullable=True)
    # Bank details encrypted at rest (Fernet) — 2026-09-20 security fix F-05.
    # Columns store ciphertext; use account_number_plain / bsb_plain for decrypted values.
    account_number = db.Column(db.String(500), nullable=True)
    bsb = db.Column(db.String(500), nullable=True)
    # NAB-issued 6-digit Direct Entry Credit User ID — embedded in ABA file
    # header positions 57-62. Added 2026-09-21 to replace the hard-coded
    # '301500' placeholder in app/shared/aba.py:build_header_record (NAB was
    # rejecting uploads with error 317651). NULL until the user supplies the
    # real ID from their NAB Connect onboarding email. Stored Fernet-encrypted
    # (F-05 pattern) — use User.de_user_id_plain to read.
    de_user_id = db.Column(db.String(500), nullable=True)
    payment_terms = db.Column(db.Integer, nullable=False, default=14)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)

    expenses = db.relationship('Expense', backref='user', lazy='dynamic')
    invoices = db.relationship('Invoice', backref='user', lazy='dynamic')
    activity_logs = db.relationship('ActivityLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self):
        self.api_key = secrets.token_hex(32)
        return self.api_key

    def generate_verification_token(self):
        self.verification_token = secrets.token_hex(32)
        return self.verification_token

    # --- Bank detail encryption accessors (F-05) ---

    @property
    def account_number_plain(self):
        """Decrypted account number. None if not set."""
        return decrypt_pii(self.account_number)

    @account_number_plain.setter
    def account_number_plain(self, value):
        self.account_number = encrypt_pii(value) if value else None

    @property
    def bsb_plain(self):
        """Decrypted BSB. None if not set."""
        return decrypt_pii(self.bsb)

    @bsb_plain.setter
    def bsb_plain(self, value):
        self.bsb = encrypt_pii(value) if value else None

    # --- DE User ID (NAB ABA file header positions 57-62) ---
    @property
    def de_user_id_plain(self):
        """Decrypted Direct Entry Credit User ID. None if not set.
        Validated to be 6 digits when read; malformed stored values
        return None rather than raising, since this is on a hot path
        for aba.py:build_header_record which explicitly handles None.
        """
        plain = decrypt_pii(self.de_user_id)
        if plain and (not plain.isdigit() or len(plain) > 6):
            return None
        return plain

    @de_user_id_plain.setter
    def de_user_id_plain(self, value):
        """Set the DE User ID. Accepts a 1-6 digit string; pads to 6 on
        storage. Strips whitespace. Raises ValueError on non-numeric input.
        """
        if value is None or value == '':
            self.de_user_id = None
            return
        stripped = str(value).strip()
        if not stripped.isdigit():
            raise ValueError(
                f'DE User ID must be all digits, got {value!r}'
            )
        if len(stripped) > 6:
            raise ValueError(
                f'DE User ID must be ≤6 digits, got {len(stripped)} in {value!r}'
            )
        # Normalise: right-justify zero-filled per ABA spec position 57-62.
        normalised = stripped.rjust(6, '0')
        self.de_user_id = encrypt_pii(normalised)

    @property
    def de_user_id_masked(self):
        """Masked representation for API responses (e.g. '••3015').
        Returns None if not set."""
        plain = self.de_user_id_plain
        if not plain:
            return None
        if len(plain) <= 2:
            return '•' * len(plain)
        return '••' + plain[-4:]

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'country': self.country,
            'email_verified': self.email_verified,
            'business_name': self.business_name,
            'abn': self.abn,
            'address_line1': self.address_line1,
            'address_line2': self.address_line2,
            'city': self.city,
            'state': self.state,
            'postcode': self.postcode,
            'address_country': self.address_country,
            'contact_email': self.contact_email,
            'contact_number': self.contact_number,
            'logo_path': self.logo_path,
            'bank_name': self.bank_name,
            'account_name': self.account_name,
            'account_number': mask_account(self.account_number_plain),
            'bsb': mask_bsb(self.bsb_plain),
            'de_user_id': self.de_user_id_masked,
            'payment_terms': self.payment_terms,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
