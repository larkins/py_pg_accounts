import uuid
from datetime import datetime, timezone
import secrets

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db, get_utc_now


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
    address = db.Column(db.Text, nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    logo_path = db.Column(db.String(500), nullable=True)
    bank_name = db.Column(db.String(255), nullable=True)
    account_name = db.Column(db.String(255), nullable=True)
    account_number = db.Column(db.String(50), nullable=True)
    bsb = db.Column(db.String(20), nullable=True)
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

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'country': self.country,
            'email_verified': self.email_verified,
            'business_name': self.business_name,
            'abn': self.abn,
            'address': self.address,
            'contact_email': self.contact_email,
            'contact_number': self.contact_number,
            'logo_path': self.logo_path,
            'bank_name': self.bank_name,
            'account_name': self.account_name,
            'account_number': self.account_number,
            'bsb': self.bsb,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
