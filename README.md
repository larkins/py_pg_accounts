# py_pg_accounts

Open-source accounting system for Australian small businesses. Tracks income
(GST), expenses (with attachments and OCR), customers, invoices, payments,
payroll, super contributions, and quarterly BAS lodgement. Includes a
browser-based HMI for manual entry, a REST API for programmatic access, a
PWA for receipt capture on mobile, and a structured Python skill for AI
agents.

## Features

- **Income & expenses** — full CRUD, vendor/amount/GST categorisation, file
  attachments.
- **Invoicing** — draft → sent → paid lifecycle with PDFs and email delivery.
- **Customers & suppliers** — structured addresses, contact details,
  statement-of-account PDFs.
- **Bank transactions** — receive-side ledger with bank provenance
  (transaction ID, BSB/account, Osko/BPay/direct-credit method).
- **Pending payment reconciliation** — link inbound Xero payment advice to
  invoices once the bank clears.
- **Quarterly BAS** — lodgement workflow with ATO-aligned GST settlement.
- **Payroll** — employees, pay events, encrypted PII at rest, payslip PDF
  generation and email delivery, super contribution exports.
- **OCR queue** — local tesseract pipeline for receipt scanning with
  manual-review fallback.
- **Reports** — profit & loss, quarterly BAS, monthly, yearly.
- **Xero export** — one-shot CSV bundle (invoices, bills, contacts) for
  importing a full financial year into Xero.

## Architecture

```
app/
  api/        Flask blueprint with REST endpoints (port 5061)
  hmi/        Flask blueprint with browser UI  (port 5062)
  pwa/        Progressive Web App for receipt capture (under HMI)
  models/     SQLAlchemy ORM models
  shared/     cross-cutting helpers (PDF generation, address parsing, …)

processes/
  ocr_processor.py    background worker that drains the OCR queue

skills/
  py_pg_accounts/     Python skill for AI agents (see SKILL.md there)

schema/
  init.sql            canonical DDL (mirrors what db.create_all() produces)

scripts/              one-shot utility scripts (backfills, exports, …)
tests/                pytest suite (136 tests)
```

## Quick start

```bash
# Install Python deps + system binaries
pip install -r requirements.txt
sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils

# Configure
cp .env.example .env       # fill in DB creds, mail server, etc.
cp config.yaml.example config.yaml

# Initialize DB (auto-creates tables on first run)
python run.py --init-db

# Start both servers (API on :5061, HMI on :5062)
python run.py
```

The default bind address is `127.0.0.1`. Pass `--host=0.0.0.0` to expose
on the LAN. All secrets (DB password, mail server credentials, payroll
encryption key) are read from the `.env` file; the systemd unit files
load it via `EnvironmentFile=`.

## Documentation

- **`AGENTS.md`** — full system reference: every endpoint, every model
  field, every background process.
- **`skills/py_pg_accounts/SKILL.md`** — agent-facing quick start (Python
  skill overview).
- **`skills/py_pg_accounts/*.md`** — feature-specific workflows: BAS,
  bank transactions, statements, payroll, OCR queue.
- **`config.yaml.example`** — every supported config knob.

## AI agent skill

```python
from skills.py_pg_accounts.accounting_skill import AccountingSkill

skill = AccountingSkill(api_key="...")   # default base_url: http://127.0.0.1:5061
expense = skill.create_expense(
    vendor_name="Acme",
    ex_gst_amount=100.00,
    expense_date="2026-03-15",
)
```

Override the base URL via the `PY_PG_ACCOUNTS_BASE_URL` environment
variable or the `base_url=` constructor kwarg.

## Development

```bash
# Activate venv
source venv/bin/activate

# Run tests
pytest tests/                        # 136 tests
pytest tests/test_payroll_exports.py # subset
```

## License

MIT — see [LICENSE](LICENSE).
