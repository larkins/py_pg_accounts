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
from .bas_lodgement import BasLodgement
from .bank_transaction import BankTransaction, BANK_TXN_METHODS, BANK_TXN_SOURCES

# Payroll models (2026-08-27 — payroll_expansion.md).
from .employee import Employee
from .pay_event import PayEvent, PAY_EVENT_STATUSES
from .pay_event_line import PayEventLine, PAY_EVENT_LINE_TYPES
from .payslip_delivery import PayslipDelivery, PAYSLIP_DELIVERY_STATUSES, PAYSLIP_RECIPIENT_KINDS
from .super_payment import SuperPayment, SUPER_PAYMENT_STATUSES

# System-wide key-value settings (added 2026-09-17 for open-source
# release — replaces hardcoded business name / fund identifiers with
# runtime-tunable values). See app/models/system_setting.py.
from .system_setting import (
    SystemSetting,
    get_setting,
    set_setting,
    seed_defaults,
    DEFAULT_SETTINGS,
)

# Aged-receivable chasing log (2026-09-08 — tracks statements/chases
# sent to customers for overdue invoices).
from .invoice_reminder import (
    InvoiceReminder,
    INVOICE_REMINDER_TYPES,
    INVOICE_REMINDER_CHANNELS,
    INVOICE_REMINDER_DIRECTIONS,
    INVOICE_REMINDER_SENDERS,
)

# Remittance advice -> bank reconciliation log (2026-09-08 — Xero payments
# must be reconciled against the bank account before the invoice is marked paid).
from .pending_payment_reconciliation import (
    PendingPaymentReconciliation,
    PENDING_RECONCILIATION_STATUSES,
)


__all__ = [
    'db', 'get_utc_now',
    'User', 'Expense', 'Invoice', 'Customer', 'AccountCategory',
    'ActivityLog', 'OcrQueue', 'BasLodgement',
    'BankTransaction', 'BANK_TXN_METHODS', 'BANK_TXN_SOURCES',
    'Employee', 'PayEvent', 'PayEventLine', 'PayslipDelivery', 'SuperPayment',
    'PAY_EVENT_STATUSES', 'PAY_EVENT_LINE_TYPES',
    'PAYSLIP_DELIVERY_STATUSES', 'PAYSLIP_RECIPIENT_KINDS',
    'SUPER_PAYMENT_STATUSES',
    'InvoiceReminder',
    'INVOICE_REMINDER_TYPES',
    'INVOICE_REMINDER_CHANNELS',
    'INVOICE_REMINDER_DIRECTIONS',
    'INVOICE_REMINDER_SENDERS',
    'PendingPaymentReconciliation',
    'PENDING_RECONCILIATION_STATUSES',
]
