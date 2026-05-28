# Agent Documentation

This document provides a summary of the accounting system for AI agents interacting with this codebase.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
cp config.yaml.example config.yaml
# Edit .env with database credentials and API keys

# Run database migrations (auto-creates tables)
python run.py --init-db

# Start servers
python run.py --host 192.168.4.44
```

## Architecture

### Servers
- **API Server**: `192.168.4.44:5061` - REST API for agent access
- **HMI (Browser UI)**: `192.168.4.44:5062` - Human interface for manual data entry

### Key Components
1. **Flask Application**: Python web framework
2. **PostgreSQL Database**: Stores all data
3. **SQLAlchemy ORM**: Database abstraction layer
4. **OCR Queue Processor**: Background worker for receipt scanning

## Authentication

### For API Access
1. User registers via HMI at `/login` → `/register`
2. After registration, user must verify email at `/verify/<token>`
3. User generates API key at `/api-key` (requires email verification)
4. API key is passed in requests for authentication

### API Authentication
```python
headers = {"X-API-Key": "user_api_key_here"}
```

### For HMI Access
- Standard email/password login at `/login`
- Session-based authentication
- Email verification NOT required for HMI login

## Database Schema

### users
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique |
| password_hash | VARCHAR(255) | bcrypt |
| api_key | VARCHAR(64) | For API access |
| email_verified | BOOLEAN | Must be TRUE before API key generation |
| verification_token | VARCHAR(64) | For email verification |

### expenses
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key |
| vendor_name | VARCHAR(255) | OCR extracted |
| ex_gst_amount | NUMERIC(12,2) | Before GST |
| gst_amount | NUMERIC(12,2) | GST amount |
| gst_type | NUMERIC(3,1) | 0 or 0.1 |
| total_amount | NUMERIC(12,2) | Including GST |
| expense_date | DATE | Date of expense |
| attachment_path | VARCHAR(500) | Path to receipt image |

### ocr_queue
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| expense_id | UUID | Foreign key to expenses |
| image_path | VARCHAR(500) | Receipt image path |
| status | VARCHAR(20) | pending/processing/completed/failed |
| extracted_data | JSONB | OCR results |
| attempts | INTEGER | Retry count |

## OCR Queue System

Receipts uploaded via PWA are processed asynchronously:

1. PWA uploads image → Creates expense with "Pending OCR" placeholder
2. OCR job queued in `ocr_queue` table with status "pending"
3. `ocr_processor.py` polls queue, calls vision model (gemma4)
4. Extracted data updates expense record
5. Job status set to "completed" or "failed"

### Vision Model Config (config.yaml)
```yaml
vision:
  ollama_host: "http://192.168.4.41:11434"
  model: "gemma4:31b"
  timeout: 2100.0
```

### Running OCR Processor
```bash
# As systemd service (recommended)
systemctl --user start py_pg_ocr_processor

# Or manually
python processes/ocr_processor.py --config config.yaml
```

## Common Operations

### Create an Expense (via API)
```bash
curl -X POST http://192.168.4.44:5061/api/expenses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "vendor_name": "Bunnings",
    "ex_gst_amount": 45.50,
    "gst_type": 0.1,
    "expense_date": "2024-03-15",
    "description": "Hardware supplies"
  }'
```

### List Expenses
```bash
curl http://192.168.4.44:5061/api/expenses \
  -H "X-API-Key: your_api_key"
```

### Generate Report
```bash
curl "http://192.168.4.44:5061/api/reports/quarterly-bas?quarter=1&year=2024" \
  -H "X-API-Key: your_api_key"
```

## Project Structure

```
py_pg_accounts/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── api/routes.py       # REST API endpoints
│   ├── hmi/routes.py        # Browser UI routes
│   ├── pwa/routes.py        # PWA routes
│   └── models/              # SQLAlchemy models
│       ├── user.py
│       ├── expense.py
│       ├── invoice.py
│       ├── ocr_queue.py
│       └── activity_log.py
├── processes/
│   └── ocr_processor.py     # OCR queue worker
├── schema/
│   └── init.sql             # Database schema
├── config.yaml              # Configuration
├── .env                     # Secrets
├── run.py                   # Entry point
└── venv/                    # Python environment
```

## Important Notes

1. **Email Verification**: Required before API key generation. Login to HMI does NOT require verification.

2. **OCR Processing**: Receipts uploaded via PWA require OCR processing. The expense will show "Pending OCR" until processed.

3. **Vision Model**: Uses Ollama with gemma4 model at `192.168.4.41:11434`. Processing is slow (~30+ seconds).

4. **Financial Year**: Australian (July 1 - June 30)

5. **GST Types**: 0 (no GST) or 0.1 (10%)

## Troubleshooting

### OCR jobs not processing
```bash
# Check OCR processor status
systemctl --user status py_pg_ocr_processor

# Check for pending jobs
psql -d py_pg_accounts -c "SELECT * FROM ocr_queue WHERE status = 'pending';"
```

### Database connection issues
```bash
# Check PostgreSQL
systemctl --user status postgresql

# Test connection
psql -d py_pg_accounts -c "SELECT 1;"
```

### View application logs
```bash
journalctl --user -u py_pg_accounts -n 50
```
