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
            'payment_terms': self.payment_terms,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
