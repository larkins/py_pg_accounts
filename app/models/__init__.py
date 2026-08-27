from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

def get_utc_now():
    return datetime.now(timezone.utc)


# Eagerly import all models so SQLAlchemy can resolve relationships at import
# time (this matches the pattern used by the rest of the app — see run.py).
from .user import User
from .expense import Expense
from .invoice import Invoice
from .customer import Customer
from .account_category import AccountCategory
from .activity_log import ActivityLog
from .ocr_queue import OcrQueue

# Payroll models (2026-08-27 — payroll_expansion.md).
from .employee import Employee
from .pay_event import PayEvent, PAY_EVENT_STATUSES
from .pay_event_line import PayEventLine, PAY_EVENT_LINE_TYPES
from .payslip_delivery import PayslipDelivery, PAYSLIP_DELIVERY_STATUSES, PAYSLIP_RECIPIENT_KINDS
from .super_payment import SuperPayment, SUPER_PAYMENT_STATUSES


__all__ = [
    'db', 'get_utc_now',
    'User', 'Expense', 'Invoice', 'Customer', 'AccountCategory',
    'ActivityLog', 'OcrQueue',
    'Employee', 'PayEvent', 'PayEventLine', 'PayslipDelivery', 'SuperPayment',
    'PAY_EVENT_STATUSES', 'PAY_EVENT_LINE_TYPES',
    'PAYSLIP_DELIVERY_STATUSES', 'PAYSLIP_RECIPIENT_KINDS',
    'SUPER_PAYMENT_STATUSES',
]
