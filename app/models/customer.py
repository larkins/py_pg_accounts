import uuid

from . import db, get_utc_now


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False, index=True)
    contact_name = db.Column(db.String(255), nullable=True)
    # Structured address (the only address representation now). 2026-09-17
    # refactor removed the legacy free-text `address` TEXT column entirely
    # to avoid drift between denormalised blob and structured columns.
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(50), nullable=True)
    postcode = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=False, default='Australia')
    contact_email = db.Column(db.String(255), nullable=True)
    abn = db.Column(db.String(20), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    gst = db.Column(db.Boolean, nullable=False, default=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)

    invoices = db.relationship('Invoice', backref='customer', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact_name': self.contact_name,
            'address_line1': self.address_line1,
            'address_line2': self.address_line2,
            'city': self.city,
            'state': self.state,
            'postcode': self.postcode,
            'country': self.country,
            'contact_email': self.contact_email,
            'abn': self.abn,
            'contact_number': self.contact_number,
            'gst': self.gst,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
