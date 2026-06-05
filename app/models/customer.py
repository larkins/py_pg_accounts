import uuid

from . import db, get_utc_now


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False, index=True)
    contact_name = db.Column(db.String(255), nullable=True)
    address = db.Column(db.Text, nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    abn = db.Column(db.String(20), nullable=True)
    contact_number = db.Column(db.String(50), nullable=True)
    gst = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)

    invoices = db.relationship('Invoice', backref='customer', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact_name': self.contact_name,
            'address': self.address,
            'contact_email': self.contact_email,
            'abn': self.abn,
            'contact_number': self.contact_number,
            'gst': self.gst,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
