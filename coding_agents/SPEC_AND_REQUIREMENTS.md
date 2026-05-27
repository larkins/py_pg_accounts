# Accounting Software Specification

## Overview
Open-source accounting software built with Python, Flask, and PostgreSQL. Designed for Australian small businesses with GST tracking and BAS reporting capabilities.

## Architecture

### Four Main Interface Components

1. **API Server** (Flask on `192.168.4.44:5061`)
   - Serves persistent AI agent interactions via REST API
   - Provides skill-based interface for expense/invoice CRUD operations
   - Supports file uploads (images, PDFs)
   - Local network only

2. **Browser HMI** (Flask on `192.168.4.44:5062`)
   - Human-machine interface for manual data entry
   - Full CRUD for expenses and invoices
   - Report generation (Quarterly P&L with GST, Yearly P&L)
   - Local network only

3. **PWA** (Flask on `/pwa` route under HMI - `192.168.4.44:5062/pwa`)
   - Progressive Web App for receipt capture
   - Mobile-friendly interface for taking photos of receipts
   - Upload directly as new expenses

4. **Agent Skill** (`skills/` folder)
   - Provides AI agent access to database operations
   - Wraps API calls for LLM/agent consumption

## Database Schema

### Tables

#### users
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique email address |
| password_hash | VARCHAR(255) | Bcrypt hashed password |
| country | VARCHAR(50) | Country code (default: 'AU') |
| api_key | VARCHAR(64) | Unique API key for agent access |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

#### account_categories
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(100) | Account type name |
| description | TEXT | Account description |
| created_at | TIMESTAMPTZ | Creation timestamp |

#### expenses
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to users |
| account_category_id | UUID | Foreign key to account_categories |
| vendor_name | VARCHAR(255) | Vendor/supplier name |
| description | TEXT | Expense description |
| ex_gst_amount | NUMERIC(12,2) | Amount excluding GST |
| gst_amount | NUMERIC(12,2) | GST amount |
| gst_type | NUMERIC(3,1) | GST type (0 or 0.1) |
| total_amount | NUMERIC(12,2) | Total including GST |
| expense_date | DATE | Date of expense |
| attachment_path | VARCHAR(500) | Path to uploaded file |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

#### invoices
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to users |
| account_category_id | UUID | Foreign key to account_categories |
| client_name | VARCHAR(255) | Client name |
| description | TEXT | Invoice description |
| ex_gst_amount | NUMERIC(12,2) | Amount excluding GST |
| gst_amount | NUMERIC(12,2) | GST amount |
| gst_type | NUMERIC(3,1) | GST type (0 or 0.1) |
| total_amount | NUMERIC(12,2) | Total including GST |
| invoice_date | DATE | Invoice date |
| due_date | DATE | Payment due date |
| attachment_path | VARCHAR(500) | Path to uploaded file |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

#### activity_logs
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to users (nullable for system) |
| action | VARCHAR(50) | CREATE, UPDATE, DELETE |
| table_name | VARCHAR(50) | Affected table |
| record_id | UUID | Affected record ID |
| old_values | JSONB | Previous values (for updates/deletes) |
| new_values | JSONB | New values (for creates/updates) |
| ip_address | VARCHAR(45) | Client IP address |
| created_at | TIMESTAMPTZ | Action timestamp |

## Business Rules

### GST Handling
- GST types: 0 (no GST), 0.1 (10% GST)
- All monetary columns use NUMERIC(12,2) to avoid rounding errors
- GST calculated as: `ex_gst_amount * gst_type`
- Total calculated as: `ex_gst_amount + gst_amount`

### Australian Financial Year
- Year runs July 1 to June 30
- Q1: July 1 - September 30
- Q2: October 1 - December 31
- Q3: January 1 - March 31
- Q4: April 1 - June 30

### Accounting Method
- Default: Accrual basis
- Income/expenses recorded when incurred, not when paid

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login (returns JWT or session)
- `POST /api/auth/api-key` - Generate API key

### Expenses
- `GET /api/expenses` - List expenses (with date filters)
- `POST /api/expenses` - Create expense
- `GET /api/expenses/<id>` - Get single expense
- `PUT /api/expenses/<id>` - Update expense
- `DELETE /api/expenses/<id>` - Delete expense
- `POST /api/expenses/<id>/upload` - Upload attachment

### Invoices
- `GET /api/invoices` - List invoices (with date filters)
- `POST /api/invoices` - Create invoice
- `GET /api/invoices/<id>` - Get single invoice
- `PUT /api/invoices/<id>` - Update invoice
- `DELETE /api/invoices/<id>` - Delete invoice
- `POST /api/invoices/<id>/upload` - Upload attachment

### Account Categories
- `GET /api/account-categories` - List categories
- `POST /api/account-categories` - Create category
- `PUT /api/account-categories/<id>` - Update category
- `DELETE /api/account-categories/<id>` - Delete category

### Reports
- `GET /api/reports/profit-loss` - P&L report (params: start_date, end_date)
- `GET /api/reports/monthly` - Monthly P&L report (params: year, month)
- `GET /api/reports/quarterly-bas` - Quarterly BAS summary
- `GET /api/reports/yearly-finances` - Yearly P&L for July-June

### Activity Logs
- `GET /api/activity-logs` - List activity logs (admin only)

## HMI Routes (Browser Interface)

### Pages
- `/` - Dashboard
- `/expenses` - Expense list and management
- `/expenses/new` - Create expense
- `/expenses/<id>/edit` - Edit expense
- `/invoices` - Invoice list and management
- `/invoices/new` - Create invoice
- `/invoices/<id>/edit` - Edit invoice
- `/reports` - Report generation interface
- `/reports/monthly` - Monthly P&L report
- `/reports/quarterly-bas` - Quarterly BAS report
- `/reports/yearly-pnl` - Yearly P&L report
- `/account-categories` - Manage account categories
- `/login` - User login
- `/logout` - User logout

## PWA Routes

### Endpoints
- `/pwa` - PWA main page
- `/pwa/capture` - Camera capture interface
- `/pwa/upload` - Process and upload receipt photo

## File Storage
- Uploaded files stored in `uploads/` directory
- Subdirectories: `expenses/`, `invoices/`, `receipts/`
- Supported formats: JPEG, PNG, PDF
- Max file size: 10MB

## Configuration

### config.yaml (untracked)
```yaml
database:
  host: localhost
  port: 5432
  name: py_pg_accounts
  user: postgres

app:
  host: "192.168.4.44"
  api_port: 5061
  hmi_port: 5062
  secret_key: "change-me-in-production"
  upload_folder: "uploads"
  max_content_length: 10485760  # 10MB

accounting:
  default_gst_type: 0.1
  financial_year_start_month: 7  # July
  financial_year_start_day: 1
  financial_year_end_month: 6  # June
  financial_year_end_day: 30
```

## Security Considerations

1. API key authentication for agent access
2. Password hashing with bcrypt
3. No credentials hardcoded - use environment variables and config files
4. Input validation on all endpoints
5. SQL injection prevention via parameterized queries (SQLAlchemy ORM)
6. CSRF protection on forms
7. File upload validation (type, size)

## Technology Stack

- **Language**: Python 3.10+
- **Virtual Environment**: `venv` (named "venv" in project root)
- **Web Framework**: Flask
- **ORM**: SQLAlchemy with Flask-SQLAlchemy
- **Database**: PostgreSQL
- **Templates**: Jinja2
- **File Uploads**: Flask-WTF / native Flask
- **Authentication**: Flask-Login for HMI, API keys for agents
- **Password Hashing**: bcrypt

## Project Structure
```
py_pg_accounts/
├── .env                     # Database credentials (untracked)
├── .env.example            # Template for .env (tracked)
├── .gitignore
├── config.yaml             # Application config (untracked)
├── config.yaml.example     # Template for config (tracked)
├── app/
│   ├── __init__.py
│   ├── api/                # API server
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── auth.py
│   │   └── reports.py
│   ├── hmi/                # Browser HMI
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── templates/
│   ├── pwa/                # PWA
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── models/            # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── expense.py
│   │   ├── invoice.py
│   │   ├── account_category.py
│   │   └── activity_log.py
│   └── shared/            # Shared utilities
│       ├── __init__.py
│       ├── decorators.py
│       └── validators.py
├── skills/                 # Agent skills
│   └── accounting_skill.py
├── systemd/                # Systemd service files (tracked)
│   └── py_pg_accounts.service
├── schema/                 # PostgreSQL schema files (tracked)
│   └── init.sql
├── venv/                   # Python virtual environment (untracked)
├── install.sh              # Installation script (tracked)
├── uploads/                # File uploads (untracked)
│   ├── expenses/
│   ├── invoices/
│   └── receipts/
├── requirements.txt
└── run.py                  # Application entry point
```

## Systemd Service

The application runs as a systemd user service using the project `venv`.

### Service File: `systemd/py_pg_accounts.service`
```
[Unit]
Description=Python PostgreSQL Accounting System
After=postgresql.service
Wants=postgresql.service

[Service]
Type=simple
Environment="PATH=%h/py_pg_accounts/venv/bin:/usr/local/bin:/usr/bin:/bin"
WorkingDirectory=%h/py_pg_accounts
ExecStart=%h/py_pg_accounts/venv/bin/python3 run.py --host 192.168.4.44
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

To install: `systemctl --user enable py_pg_accounts.service`
To start: `systemctl --user start py_pg_accounts.service`
To view logs: `journalctl --user -u py_pg_accounts.service`

## PostgreSQL Schema

Database schema is stored in `schema/init.sql` for manual setup or automation.

## Installation

Run `install.sh` to:
1. Copy `.env.example` to `.env`
2. Copy `config.yaml.example` to `config.yaml`
3. Initialize the PostgreSQL schema
4. Install the systemd user service
5. Display reminder to modify configuration files
