# Accounting Skill Documentation

A structured interface for AI agents to interact with the accounting system, wrapping the REST API to provide natural language access to expense, invoice, customer, and business profile management.

## Quick Start

```python
from skills.accounting_skill import AccountingSkill

skill = AccountingSkill(
    api_key="your-api-key-here",
    # base_url is optional — defaults to http://127.0.0.1:5061.
    # Override via the `base_url=` kwarg or the PY_PG_ACCOUNTS_BASE_URL env var.
)

# Create an expense
expense = skill.create_expense(
    vendor_name="Bunnings",
    amount=100.00,
    expense_date="2024-03-15",
    gst_type=0.1
)

# List invoices
invoices = skill.list_invoices(start_date="2024-01-01", end_date="2024-03-31")

# Generate an invoice PDF
skill.download_invoice_pdf(invoice_id=invoices[0]["id"], save_path="./invoice.pdf")
```

## Authentication

All API requests (except registration) require an `X-API-Key` header:

```python
headers = {"X-API-Key": "your-api-key-here"}
```

The skill handles this automatically when you instantiate it with your API key.

### Getting an API Key

1. Register via HMI at `/login` → `/register`
2. Verify your email at `/verify/<token>`
3. Generate an API key at `/api-key` (requires email verification)

## Business Profile Management

Each user has a business profile that appears on invoice PDFs. The business name, ABN, address, contact email, and contact number are shown on the right of the PDF header, with the logo on the left.

### Update Business Details

The `update_business_details()` method is used to create or update all business profile fields including bank details. There's no separate "create" endpoint for bank details - they're set as part of the business profile.

```python
skill.update_business_details(
    business_name="Acme Pty Ltd",
    abn="12345678901",
    address="123 Main St\nSydney NSW 2000",
    contact_email="billing@acme.com",
    contact_number="+61 2 1234 5678",
    bank_name="Commonwealth Bank",
    account_name="Acme Pty Ltd",
    bsb="062-001",
    account_number="12345678",
    payment_terms=14
)
```

To clear a bank detail field, pass an empty string:

```python
skill.update_business_details(
    bank_name="",
    account_name="",
    account_number="",
    bsb=""
)
```

### Bank Details

Bank details are stored on the user/business profile and appear on invoice PDFs (at the bottom). They are managed via the same `update_business_details()` method.

**Set/Update bank details:**

```python
skill.update_business_details(
    bank_name="Commonwealth Bank",
    account_name="Acme Pty Ltd",
    bsb="062-001",
    account_number="12345678"
)
```

**Clear (delete) bank details:**

There is no separate "delete" endpoint. To clear a bank detail, set it to an empty string:

```python
skill.update_business_details(
    bank_name="",
    account_name="",
    bsb="",
    account_number=""
)
```

**Read bank details:**

```python
profile = skill.get_business_details()
print(profile['bank_name'])
print(profile['account_name'])
print(profile['bsb'])
print(profile['account_number'])
```

Bank details only appear on the invoice PDF if at least one field is populated. The section is automatically hidden if all bank fields are empty.

### Payment Terms

Each user has a `payment_terms` setting (in days) that controls the "Payment terms: Net X days" line on invoice PDFs. The default is 14 days.

This value should be consistent with the due date set on each invoice (due_date = invoice_date + payment_terms days).

**Set/Update payment terms:**

```python
skill.update_business_details(
    payment_terms=30  # 30-day terms
)
```

**Read payment terms:**

```python
profile = skill.get_business_details()
print(f"Default payment terms: {profile['payment_terms']} days")
```

### Upload Business Logo

The logo appears in the top-left of every invoice PDF.

```python
skill.upload_logo("/path/to/logo.png")
```

Supported formats: PNG, JPG, JPEG, GIF, WEBP, SVG

### Delete Logo

```python
skill.delete_logo()
```

## Customer Management

Customers are stored in a separate table and are **required** for invoice creation. This ensures consistent customer information across invoices.

### Create a Customer

```python
customer = skill.create_customer(
    name="Acme Corp",
    contact_name="John Smith",
    address="456 Business Ave\nMelbourne VIC 3000",
    contact_email="accounts@acme.com",
    abn="98765432109",
    contact_number="+61 3 9876 5432",
    gst=True
)
```

### List Customers

```python
customers = skill.list_customers()
for c in customers:
    print(f"{c['name']} - ABN: {c['abn']}")
```

### Update a Customer

```python
skill.update_customer(
    customer_id="abc-123",
    contact_email="newemail@acme.com"
)
```

### Delete a Customer

Cannot delete a customer with existing invoices:

```python
skill.delete_customer(customer_id="abc-123")
```

## Expense Management

Expenses can be created via API, the HMI browser form, or the PWA receipt capture. Each expense has a `source` field tracking origin (`api`, `browser`, or `pwa`).

### Create an Expense

```python
expense = skill.create_expense(
    vendor_name="Office Supplies",
    amount=100.00,
    expense_date="2024-03-15",
    gst_type=0.1,  # 10% GST
    amount_type="excludes",  # or "includes"
    currency="AUD",  # or "USD"
    description="Pens and paper",
    account_category_id="category-uuid"  # optional
)
```

### List Expenses with Date Filter

```python
expenses = skill.list_expenses(
    start_date="2024-01-01",
    end_date="2024-03-31"
)
```

### Upload Receipt Attachment

```python
skill.upload_expense_attachment(
    expense_id="expense-uuid",
    file_path="/path/to/receipt.jpg"
)
```

### Update / Delete

```python
skill.update_expense(expense_id="...", vendor_name="New Name")
skill.delete_expense(expense_id="...")
```

## Invoice Management

Invoices require a `customer_id`. Each invoice is tied to a customer record so customer details are consistent.

### Create an Invoice

```python
invoice = skill.create_invoice(
    customer_id="customer-uuid",  # REQUIRED
    client_name="Acme Corp",  # Display name (can be different from customer.name)
    ex_gst_amount=1000.00,
    invoice_date="2024-03-15",
    gst_type=0.1,
    description="Consulting services for Q1",
    due_date="2024-04-15",  # optional
    status="draft",  # optional: draft, sent, paid, overdue, cancelled
    payment_date=None,  # optional: YYYY-MM-DD
    amount_paid=None  # optional: numeric
)
```

### Mark an Invoice as Paid

```python
# Mark as fully paid (uses today as payment date, total_amount as amount_paid, paid_at = now)
paid_invoice = skill.mark_invoice_paid(invoice_id="invoice-uuid")

# Mark as paid with custom date and amount
paid_invoice = skill.mark_invoice_paid(
    invoice_id="invoice-uuid",
    payment_date="2024-04-10",
    amount_paid=1100.00  # for partial payments
)
```

### Mark an Invoice as Sent

```python
# Mark as sent (sets status='sent', sent_at = now)
sent_invoice = skill.mark_invoice_sent(invoice_id="invoice-uuid")

# Mark as sent with custom timestamp
sent_invoice = skill.mark_invoice_sent(
    invoice_id="invoice-uuid",
    sent_at="2024-04-08T10:30:00Z"
)
```

### Mark an Invoice as Confirmed Received

```python
# Mark as confirmed received (sets confirmed_received_at = now)
confirmed = skill.mark_invoice_confirmed(invoice_id="invoice-uuid")

# Mark as confirmed with custom timestamp
confirmed = skill.mark_invoice_confirmed(
    invoice_id="invoice-uuid",
    confirmed_received_at="2024-04-09T14:22:00Z"
)
```

### Update Invoice Status

```python
# Update via the general update_invoice method
invoice = skill.update_invoice(
    invoice_id="invoice-uuid",
    status="sent"  # or "draft", "paid", "overdue", "cancelled"
)

# Or update with payment details
invoice = skill.update_invoice(
    invoice_id="invoice-uuid",
    status="paid",
    payment_date="2024-04-10",
    amount_paid=1100.00
)
```

**Invoice statuses:** `draft`, `sent`, `paid`, `overdue`, `cancelled`

**Lifecycle timestamps:**
- `sent_at` - automatically set by `mark_invoice_sent()`
- `confirmed_received_at` - automatically set by `mark_invoice_confirmed()`
- `paid_at` - automatically set by `mark_invoice_paid()`

### Download Invoice PDF

Generates a professional PDF with the user's logo, business details, bank details, customer info, line items, and totals. Saves to local file:

```python
path = skill.download_invoice_pdf(
    invoice_id="invoice-uuid",
    save_path="./invoice.pdf"
)
```

**PDF contents:**
- **Header (left)**: User's business logo (if uploaded)
- **Header (right)**: Business name, ABN, address, contact email/phone
- **Title**: "INVOICE" with invoice number
- **Info block**: Invoice date, due date, invoice number
- **Bill To**: Customer name, contact person, address, contact details, ABN
- **Description**: Optional invoice description
- **Line items table**: Itemized charges
- **Totals**: Subtotal, GST, total
- **Bank Details**: Bank name, account name, BSB, account number (when provided)
- **Footer**: Payment terms "Net X days" using user's payment_terms setting (when ABN is registered)

### List Invoices with Date Filter

```python
invoices = skill.list_invoices(
    start_date="2024-01-01",
    end_date="2024-03-31"
)
```

### Update / Delete

```python
skill.update_invoice(invoice_id="...", ex_gst_amount=1200.00)
skill.delete_invoice(invoice_id="...")
```

## Account Categories

Used to classify expenses and invoices for reporting.

```python
# Create
category = skill.create_account_category(
    name="Office Supplies",
    description="Stationery and equipment"
)

# List
categories = skill.list_account_categories()

# Update
skill.update_account_category(category_id="...", description="Updated")

# Delete
skill.delete_account_category(category_id="...")
```

## Reports

### Profit & Loss Report

```python
report = skill.get_profit_loss_report(
    start_date="2024-01-01",
    end_date="2024-03-31"
)
# Returns: income, expenses, gst_collected, gst_paid, net_income, category breakdown
```

### Quarterly BAS Report (Australian GST)

```python
report = skill.get_quarterly_bas_report(year=2024, quarter=1)
# Returns: gst_collected (1A), gst_paid (1B), net_gst (1C or 9)
```

Australian financial quarters:
- Q1: July 1 - September 30
- Q2: October 1 - December 31
- Q3: January 1 - March 31
- Q4: April 1 - June 30

### Monthly Report

```python
report = skill.get_monthly_report(year=2024, month=3)
```

### Yearly Financial Report

```python
report = skill.get_yearly_finances_report(year=2024)
# Australian financial year: July 1, 2024 to June 30, 2025
```

## Common Workflows

### Create a Customer and Invoice

```python
# 1. Create the customer
customer = skill.create_customer(
    name="Acme Corp",
    contact_email="billing@acme.com"
)

# 2. Create an invoice for that customer
invoice = skill.create_invoice(
    customer_id=customer["id"],
    client_name="Acme Corp",
    ex_gst_amount=1500.00,
    invoice_date="2024-03-15",
    due_date="2024-04-15"
)

# 3. Download the PDF
skill.download_invoice_pdf(invoice_id=invoice["id"], save_path="./invoice.pdf")
```

### Setup Business Profile for PDF Branding

```python
# 1. Set business details
skill.update_business_details(
    business_name="My Company Pty Ltd",
    abn="12345678901",
    address="123 Main St\nSydney NSW 2000",
    contact_email="accounts@mycompany.com",
    contact_number="+61 2 1234 5678",
    bank_name="Commonwealth Bank",
    account_name="My Company Pty Ltd",
    bsb="062-001",
    account_number="12345678",
    payment_terms=14
)

# 2. Upload logo
skill.upload_logo("/path/to/logo.png")
```

### Record Receipt from PWA

The PWA uploads the photo and creates the expense automatically (no API call needed). OCR extraction happens asynchronously via the OCR queue. Once processed, the expense has full details. If OCR fails, the expense is flagged with `requires_review=True` and `vendor_name="REQUIRES REVIEW"`.

To fix a failed OCR expense, use the HMI edit form to update the details, which will clear the `requires_review` flag.

## Error Handling

The skill uses `requests` and will raise `HTTPError` on non-2xx responses. Wrap calls in try/except:

```python
try:
    invoice = skill.create_invoice(...)
except requests.exceptions.HTTPError as e:
    print(f"API error: {e.response.json()}")
```

## Field Reference

### GST Types
- `0` - No GST
- `0.1` - 10% GST (Australia)

### Amount Types
- `"excludes"` - Amount is ex-GST (default)
- `"includes"` - Amount is inc-GST (will be converted)

### Currencies
- `"AUD"` - Australian Dollar (default)
- `"USD"` - US Dollar (auto-converted using Twelve Data API)

### Date Format
All dates use ISO 8601 format: `YYYY-MM-DD`

## Architecture Notes

- **Base URL**: `http://127.0.0.1:5061` (default; override with `base_url` parameter or `PY_PG_ACCOUNTS_BASE_URL` env var)
- **Authentication**: `X-API-Key` header
- **Response Format**: All responses are JSON
- **PDF Generation**: Server-side using ReportLab
- **OCR**: Receipt images processed asynchronously via gemma4 vision model

## Requirements

```bash
pip install requests
```

No other dependencies - the skill uses only the Python standard library plus `requests`.
