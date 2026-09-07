# Payroll

Per-business employee master + pay events (the actual payslips) + superannuation remittances + summary/dashboard endpoints. PII fields (TFN, bank BSB, bank account number) are encrypted at rest via Fernet (`PAYROLL_PII_KEY` in `.env`).

## High-level model

```
Employee (master record)
   |
   |---< PayEvent (one per payslip issued)
   |          |
   |          |---< PayEventLine (itemised earnings/deductions)
   |          |
   |          |---< PayslipDelivery (audit trail of every email sent)
   |
   |---< SuperPayment (one per actual fund remittance, covering one+ PayEvents)
```

## Resources

| Resource | Description |
|---|---|
| Employee | Master record per worker. PII-encrypted. Status: `active` \| `terminated`. |
| PayEvent | One per payslip. Has headline amounts (gross, net, PAYG) + itemised lines. Status: `draft` \| `finalized` \| `paid` \| `cancelled`. |
| PayEventLine | Itemised breakdown of a PayEvent (earnings, tax, deductions, allowances, employer contributions). |
| PayslipDelivery | Audit row per recipient per send (one PayEvent can have multiple deliveries — work email + personal email + cc to manager). |
| SuperPayment | One per actual fund remittance. Covers one or more PayEvents. Status: `pending` \| `paid` \| `reconciled`. |

## Status flows

```
Employee:        active ----terminate()----> terminated

PayEvent:        draft ----finalize()----> finalized ----mark_paid()----> paid
                       \---cancel()------> cancelled

SuperPayment:    pending ----mark_paid()----> paid ----reconcile()----> reconciled
```

## API endpoints

### Employees (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/payroll/employees?status=active` | List (filter by status) |
| POST | `/api/payroll/employees` | Create |
| GET | `/api/payroll/employees/<id>` | Get one (PII fields decrypted for caller) |
| PUT | `/api/payroll/employees/<id>` | Update |
| POST | `/api/payroll/employees/<id>/terminate` | Set `employment_status='terminated'` + `end_date` |

### Pay Events (8)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/payroll/pay-events?employee_id=&start_date=&end_date=&status=` | List |
| POST | `/api/payroll/pay-events` | Create draft |
| GET | `/api/payroll/pay-events/<id>` | Get one (with lines) |
| PUT | `/api/payroll/pay-events/<id>` | Update (only when status=draft) |
| POST | `/api/payroll/pay-events/<id>/finalize` | Lock amounts (draft → finalized) |
| POST | `/api/payroll/pay-events/<id>/mark-paid` | Mark as paid |
| POST | `/api/payroll/pay-events/<id>/cancel` | Cancel (any status except cancelled) |
| GET | `/api/payroll/pay-events/<id>/pdf` | Download payslip PDF |
| POST | `/api/payroll/pay-events/<id>/send-payslip` | Email the PDF + record PayslipDelivery |

### Super Payments (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/payroll/super-payments` | List |
| POST | `/api/payroll/super-payments` | Create (remittance record) |
| GET | `/api/payroll/super-payments/<id>` | Get one |
| POST | `/api/payroll/super-payments/<id>/mark-paid` | pending → paid |
| POST | `/api/payroll/super-payments/<id>/reconcile` | paid → reconciled |

### Summary (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/payroll/summary` | Top-level dashboard |
| GET | `/api/payroll/summary/ytd` | Year-to-date (Australian FY) |
| GET | `/api/payroll/summary/super-owing` | Outstanding super per employee |
| GET | `/api/payroll/summary/payg-withheld` | PAYG totals (for BAS) |
| GET | `/api/payroll/summary/recent-deliveries?limit=20` | Recent payslip email audit |

## Common workflows

### Weekly payroll run example

A typical weekly payroll run for a full-time Australian employee under the National Employment Standards (NES):

```python
from datetime import date, timedelta
from decimal import Decimal
from skills.py_pg_accounts.accounting_skill import AccountingSkill

skill = AccountingSkill(api_key="...")

# 1. Look up the employee
employee = skill.get_employee(employee_id="<your-employee-uuid>")
legal_name = employee['legal_name']

# 2. Compute the period (Mon to Sun, paid the following Monday)
today = date.today()
last_monday = today - timedelta(days=today.weekday() + 7)  # previous Monday
last_sunday = last_monday + timedelta(days=6)              # previous Sunday
payment_date = last_monday + timedelta(days=7)              # this Monday

# 3. Rate + hours config (substitute your own)
hourly_rate = 50.00
standard_week_hours = 38
gross = Decimal(hourly_rate) * Decimal(standard_week_hours)   # 1900.00
# tax withheld (compute via PAYG tables — out of scope here)
payg = compute_payg_tax(gross)
net = gross - payg
super_rate = Decimal('0.12')   # 12% OTE
super_payable = (gross * super_rate).quantize(Decimal('0.01'))  # 228.00

# 4. Create draft pay event
pay_event = skill.create_pay_event(
    employee_id=employee['id'],
    payment_date=payment_date.isoformat(),
    pay_period_start=last_monday.isoformat(),
    pay_period_end=last_sunday.isoformat(),
    gross_amount=float(gross),
    net_amount=float(net),
    payg_tax_amount=float(payg),
    pay_frequency='weekly',
    super_ote_amount=float(gross),
    super_payable_amount=float(super_payable),
    bank_reference=f"EMP {last_monday.strftime('%Y%m%d')}",
    lines=[
        {
            'line_type': 'ordinary_hours',
            'description': 'Ordinary hours (38h @ $50/h)',
            'quantity': 38, 'rate': 50.00,
            'amount': float(gross), 'is_taxable': True, 'sort_order': 1,
        },
        {
            'line_type': 'tax',
            'description': 'PAYG tax withheld',
            'amount': float(payg), 'is_taxable': False, 'sort_order': 2,
        },
        {
            'line_type': 'net_pay',
            'description': 'Net pay',
            'amount': float(net), 'is_taxable': False, 'sort_order': 3,
        },
        {
            'line_type': 'employer_super',
            'description': 'Super 12% OTE',
            'amount': float(super_payable), 'is_taxable': False, 'sort_order': 4,
        },
    ],
)

# 5. Finalize (locks the amounts)
finalized = skill.finalize_pay_event(pay_event_id=pay_event['id'])

# 6. Generate PDF
skill.generate_payslip_pdf(
    pay_event_id=finalized['id'],
    save_path=f"./payslips/{employee['id'][:8]}_{payment_date.isoformat()}.pdf",
)

# 7. Send to employee (defaults to email_work, 'work' recipient_kind)
delivery = skill.send_payslip(pay_event_id=finalized['id'])

# 8. Mark paid (after the bank debit clears)
paid = skill.mark_pay_event_paid(pay_event_id=finalized['id'])

# 9. (Optional) Record the super remittance when you actually pay the fund
# ... usually done weekly or quarterly depending on the fund
```

### Quarterly super reconciliation

```python
# At end of quarter, find what's owing
owing = skill.super_owing()
for emp_id, data in owing['employees'].items():
    print(f"{data['employee_name']}: ${data['total_owing']} "
          f"({len(data['unremitted_pay_events'])} unremitted pay events)")

# Group unremitted pay events by employee and create a SuperPayment per fund
for emp in owing['employees'].values():
    skill.create_super_payment(
        employee_id=emp['employee_id'],
        remittance_date='2026-09-28',
        amount=emp['total_owing'],
        pay_event_ids=[pe['id'] for pe in emp['unremitted_pay_events']],
        fund_name_snapshot=emp['super_fund_name'],     # snapshot at remittance
        fund_member_snapshot=emp['super_fund_member_no'],
        payment_reference=f"Q4-{emp['employee_id'][:8]}",
    )

# After the super fund clears the payment, mark each as paid then reconciled
for sp in skill.list_super_payments(status='pending')['super_payments']:
    skill.mark_super_paid(sp_id=sp['id'])
    # ... when the quarterly statement arrives from the fund:
    skill.reconcile_super(sp_id=sp['id'])
```

### Find payslip email delivery failures

```python
recent = skill.recent_payslip_deliveries(limit=50)
failures = [d for d in recent if d.get('delivery_status') == 'failed']
for f in failures:
    print(f"Pay event {f['pay_event_id'][:8]}: {f['recipient_email']} - {f.get('error_message')}")
```

### Terminate an employee

```python
skill.terminate_employee(
    employee_id="...",
    end_date="2026-09-30",
    reason="Resigned - moving to NSW",
)
# Sets employment_status='terminated' and end_date. Existing pay events stay.
```

## PII handling

PII columns (tfn, bank_bsb, bank_account_number) are encrypted via Fernet in `app/shared/pii.py`. The encryption key is `PAYROLL_PII_KEY` in `.env` (must be set or the model refuses to load — see `raise RuntimeError` in pii.py).

The API decrypts PII on GET responses (so callers see plaintext bank details etc.). When you PUT back the same value, it's re-encrypted with the current key. **Never log or store PII in plaintext outside the API.**

## Locked fields

`PayEvent` headline amounts (gross, net, payg, super_ote, super_payable) are **immutable after finalize**. To change a finalized pay event, cancel it and create a new one. Lines are similarly locked.

This is enforced at the API layer — PUT returns 400 if you try to mutate a finalized event.

## PayEvent line types

| line_type | Use |
|---|---|
| `ordinary_hours` | Standard hours (e.g. 38h/week for AU NES) |
| `overtime_hours` | Overtime at 1.5x or 2x |
| `leave_loading` | Annual leave loading (17.5% in AU) |
| `allowance` | Carers, mobile, uniform, etc. |
| `bonus` | Discretionary |
| `tax` | PAYG withholding (negative amount on net pay calc) |
| `deduction` | Salary sacrifice, child support garnishment |
| `employer_super` | Super contribution from employer |
| `net_pay` | Final take-home (informational; the actual net_amount headline is the truth) |

`is_taxable=False` lines don't count toward super OTE.

## PAYG tax computation

The skill doesn't compute PAYG tax — that's a separate concern (PAYG withholding schedules vary by residency, tax-free threshold declaration, STSL/HECS debt, etc.). The payroll pipeline expects you to compute `payg_tax_amount` externally and pass it in.

PAYG tax must be computed externally using the ATO withholding schedules (residents, HELP/HECS debt, tax-free threshold declaration, etc.). The skill expects you to pass in the computed `payg_tax_amount`.

## Related

- See `SKILL.md` for general skill setup
- `get_payg_withheld()` in the skill returns PAYG totals for BAS reporting — feed into `BAS.md` workflow
- See `bank-transactions.md` for recording the bank debit that settles the super payment
