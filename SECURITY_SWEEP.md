# Security Audit — py_pg_accounts

**Date:** 2026-09-20
**Scope:** Full codebase audit (all API routes, HMI routes, PWA routes, models, shared utilities, config, schema)
**Classification:** Internal — contains sensitive architectural details

---

## 1. Executive Summary

py_pg_accounts is a Flask + PostgreSQL accounting application handling financial data (invoices, expenses, payroll, BAS) and employee PII (TFN, DOB, bank details). The application demonstrates a solid foundation with Fernet encryption for PII at rest, user-scoped queries on most endpoints, and an activity audit log. However, several critical and high-severity issues must be addressed before this application handles production financial data.

### Finding Counts

| Severity | Count |
|----------|-------|
| **Critical** | 4 |
| **High** | 7 |
| **Medium** | 8 |
| **Low** | 5 |
| **Informational** | 3 |

### Top Risks

1. **No CSRF protection** on any HMI form — all state-changing web routes are vulnerable to cross-site request forgery
2. **Default secret key** (`'dev-secret-key'`) — Flask session cookies can be forged if the default is not overridden
3. **No rate limiting** on any endpoint, including auth (login, register) and API key generation
4. **User bank details in plaintext** — `account_number` and `bsb` on the User model are stored unencrypted and returned in `to_dict()`
5. **Open registration** — both API and HMI registration endpoints allow anyone to create an account
6. **No session cookie security flags** — no `Secure`, `HttpOnly`, or `SameSite` configuration
7. **Verification token flashed in plaintext** — email verification tokens are displayed in the browser via flash messages

---

## 2. Security Architecture Overview

### Application Structure

```
py_pg_accounts/
├── run.py                    # Entry point — starts API (5061) + HMI (5062) servers
├── app/
│   ├── __init__.py           # App factory, blueprint registration, config loading
│   ├── api/                  # REST API blueprints (all @api_key_required)
│   │   ├── routes.py         # Core CRUD: auth, customers, expenses, invoices, OCR queue
│   │   ├── payroll.py        # Payroll: employees, pay events, super payments, summaries
│   │   ├── payroll_exports.py# ABA bank file + super CSV exports
│   │   ├── bank_transactions.py  # Bank transaction recording + reconciliation
│   │   ├── bas.py            # BAS lodgement tracking
│   │   ├── invoice_reminders.py  # Invoice reminder/chase logging
│   │   ├── payment_reconciliations.py  # Pending payment reconciliation
│   │   ├── reports.py        # P&L, BAS, monthly, yearly reports
│   │   ├── settings.py       # System settings CRUD
│   │   └── xero_export.py    # Xero CSV export (ZIP)
│   ├── hmi/                  # Human Machine Interface (server-rendered HTML)
│   │   ├── routes.py         # Login, dashboard, expenses, invoices, reports, settings
│   │   └── payroll.py        # Payroll HMI: employees, pay events, super, exports
│   ├── pwa/                  # Progressive Web App (mobile receipt capture)
│   │   └── routes.py         # Login, receipt upload, OCR queue
│   ├── models/               # SQLAlchemy models
│   └── shared/               # Utilities: auth decorators, PII encryption, PDF, validators
├── schema/init.sql           # Authoritative PostgreSQL schema
├── .env.example              # Environment variable template
└── requirements.txt          # Python dependencies
```

### Authentication Model

The application supports two authentication methods:

1. **API Key** (`X-API-Key` header) — for programmatic API access. Generated via `POST /api/auth/api-key` (requires existing auth) or HMI web UI.
2. **Session Cookie** — for HMI (web UI) and PWA (mobile) users. Flask session with `user_id` stored server-side.

Both methods are handled by `app/shared/decorators.py::_resolve_current_user()`.

### Data Sensitivity Classification

| Data | Sensitivity | Protection |
|------|------------|------------|
| Employee TFN | **High** (tax ID) | Fernet encrypted at rest |
| Employee DOB | **High** (identity) | Fernet encrypted at rest |
| Employee bank BSB/account | **High** (financial) | Fernet encrypted at rest |
| User bank BSB/account | **High** (financial) | **PLAINTEXT** — no encryption |
| Invoice amounts | Medium (financial) | Plaintext (needed for computation) |
| Expense amounts | Medium (financial) | Plaintext |
| Customer details | Medium (business) | Plaintext |
| User password | **High** | werkzeug `generate_password_hash` (PBKDF2) |
| API keys | **High** | `secrets.token_hex(32)`, stored plaintext in DB |
| Flask SECRET_KEY | **Critical** | Env var, defaults to `'dev-secret-key'` |
| PAYROLL_PII_KEY | **Critical** | Env var, no default (fails fast) |

---

## 3. Authentication & Authorization

### 3.1 Authentication Mechanisms

**Password authentication** (`app/models/user.py`):
- Uses `werkzeug.security.generate_password_hash` / `check_password_hash` (PBKDF2-SHA256 by default)
- No password complexity requirements enforced
- No password history or rotation policy
- No account lockout after failed attempts

**API key authentication** (`app/models/user.py`):
- `secrets.token_hex(32)` — 256-bit random hex key, cryptographically secure
- Stored as plaintext in the `users.api_key` column (VARCHAR(64))
- Transmitted via `X-API-Key` header
- No key rotation policy, no expiry, no scope limitation

**Session authentication** (HMI + PWA):
- Flask session cookie with `user_id` stored server-side
- No session timeout configured
- No session fixation protection (session ID not rotated on login)
- PWA uses a separate session key (`pwa_user_id`) but the same underlying Flask session

### 3.2 Authorization Model

**User scoping** is the primary authorization mechanism. Most queries filter by `user_id`:

```python
# Good pattern — used consistently for expenses, invoices, pay events, etc.
Expense.query.filter_by(id=expense_id, user_id=request.current_user.id).first()
```

**Customer model is NOT user-scoped** — `Customer.query.get(customer_id)` without a `user_id` filter. This is intentional per code comments ("customers are not user-scoped"), but it means any authenticated user can read, update, or delete any customer record.

**No role-based access control (RBAC)** — all authenticated users have the same permissions. There is no admin/user/viewer distinction.

### 3.3 Critical Auth Findings

See findings F-01 through F-06 in Section 11.

---

## 4. Data Protection

### 4.1 PII Encryption at Rest

**Employee PII** (`app/shared/pii.py`):
- Algorithm: Fernet (AES-128-CBC with HMAC-SHA256 for authentication)
- Key source: `PAYROLL_PII_KEY` environment variable
- Key management: Single key, loaded at module import, no rotation support
- Encrypted columns: `tfn`, `date_of_birth`, `bank_bsb`, `bank_account_number`
- Masking: `to_dict()` returns masked values by default (`*** *** 250`, `***-456`, `*****678`)
- Plaintext access: `*_plain` properties decrypt on demand
- Fail-fast: App refuses to start if `PAYROLL_PII_KEY` is missing or invalid

**Assessment:** Solid implementation. Fernet provides authenticated encryption. The masking-by-default pattern in `to_dict()` is good. The `?reveal=true` query parameter for plaintext access is tenant-scoped (user can only see their own employees' PII).

**Gap:** User's own bank details (`User.account_number`, `User.bsb`) are stored in **plaintext** and returned in `User.to_dict()`. These are the business's own bank details that appear on invoices — they need to be readable for PDF generation, but they should still be encrypted at rest or at minimum excluded from API responses.

### 4.2 Data in Transit

- The application binds to `127.0.0.1` by default (localhost only) — good for local deployment
- No TLS/HTTPS termination in the application itself — relies on a reverse proxy (nginx, Caddy) for HTTPS
- No HSTS headers set
- The mail server API is called over HTTP (`http://127.0.0.1:5003`) — acceptable for localhost but should use HTTPS if the mail server is on a different host

### 4.3 Activity Logging

`ActivityLog` records all CRUD operations with `old_values` and `new_values` as JSON. This is a good audit trail but has a significant issue:

**Employee `to_dict()` is called for activity logs without `include_pii_plain=True`**, which means masked PII is logged. However, the `old_values` and `new_values` JSON blobs include all fields from `to_dict()`, which includes masked PII. This is acceptable — the actual ciphertext is not logged, and the masked values are safe for audit purposes.

**However**, `User.to_dict()` includes `account_number` and `bsb` in plaintext. When business details are updated via `PUT /api/auth/business`, the activity log stores the old and new bank account numbers in plaintext in the `activity_logs` table.

---

## 5. Input Validation & Injection Prevention

### 5.1 SQL Injection

**Assessment: LOW RISK.** All database queries use SQLAlchemy ORM with parameterized queries. No raw SQL or string formatting in queries was found anywhere in the codebase.

The schema file (`schema/init.sql`) uses raw SQL but is only run manually during initial setup.

### 5.2 Input Validation

**Validators** (`app/shared/validators.py`):
- `validate_uuid()` — UUID format validation
- `validate_decimal()` — Decimal parsing with min/max bounds
- `validate_date_string()` — ISO date parsing
- `validate_gst_type()` — Restricted to 0 or 0.1

**Coverage:** Most API endpoints validate UUIDs, dates, and decimals. However:

- **Email validation is absent** — `register()` and `login()` accept any string as an email address without format validation
- **Password strength is not validated** — no minimum length, complexity, or common-password check
- **String length limits are not enforced** at the application layer (only DB column limits)
- **Currency code validation** is minimal — only checks for 'USD' specifically, accepts any other 3-char string
- **Phone number, ABN, TFN format validation** — no format checking on these fields

### 5.3 XSS (Cross-Site Scripting)

**Server-rendered templates** (HMI): Jinja2 auto-escapes by default. No `|safe` filters or `mark_safe()` calls were found in the Python code. Templates were not individually audited, but the risk is low if Jinja2 auto-escaping is not disabled.

**JSON API responses:** Content-Type is `application/json` — not exploitable for XSS in modern browsers.

**PDF generation:** ReportLab Paragraph objects accept HTML-like markup (`<b>`, `<i>`, `<font>`). User-supplied data (business name, customer name, description) is interpolated into Paragraph strings without escaping. If a customer name contains `<script>alert(1)</script>`, it would be rendered as literal text in the PDF (ReportLab doesn't execute JavaScript), but malicious markup like `<font color="red">` could alter the PDF appearance. This is a low-risk finding since PDFs are not interactive.

---

## 6. Session & Cookie Security

### 6.1 Flask Session Configuration

**No session cookie security flags are configured anywhere in the application:**

```python
# app/__init__.py — no SESSION_COOKIE_* settings
app.config['SECRET_KEY'] = config['app'].get('secret_key', 'dev-secret-key')
```

Missing configurations:
- `SESSION_COOKIE_SECURE` — not set (cookie sent over HTTP)
- `SESSION_COOKIE_HTTPONLY` — not set (defaults to True in Flask 2.x, but should be explicit)
- `SESSION_COOKIE_SAMESITE` — not set (defaults to None in Flask 2.x)
- `PERMANENT_SESSION_LIFETIME` — not set (sessions never expire by default)
- `SESSION_REFRESH_EACH_REQUEST` — not set

### 6.2 Session Fixation

The login view does not rotate the session ID after authentication:

```python
# app/hmi/routes.py — login()
session['user_id'] = user.id
session['user_email'] = user.email
# No session.regenerate() or equivalent
```

Flask's default session implementation (client-side cookies) is inherently resistant to server-side session fixation, but the session cookie value persists across login/logout. An attacker who obtains a pre-login session cookie can use it post-login.

### 6.3 Secret Key

The default `SECRET_KEY` is `'dev-secret-key'`:

```python
# app/__init__.py line 24
'secret_key': os.environ.get('SECRET_KEY', 'dev-secret-key'),
```

If the `SECRET_KEY` environment variable is not set, Flask session cookies can be forged by anyone who knows the default key. This gives full session hijacking capability.

---

## 7. API Security

### 7.1 Authentication Coverage

All API endpoints (except `/api/auth/register` and `/api/auth/login`) are protected by `@api_key_required`. The decorator correctly rejects requests with neither a valid API key nor a valid session.

**Unauthenticated endpoints:**
- `POST /api/auth/register` — open registration
- `POST /api/auth/login` — credential check
- `GET /health` — health check (no sensitive data)

### 7.2 Rate Limiting

**No rate limiting is implemented anywhere in the application.** This affects:

- `POST /api/auth/login` — brute-force password guessing
- `POST /api/auth/register` — account enumeration / spam registration
- `POST /api/auth/api-key` — API key generation (requires auth, but still unlimited)
- `POST /hmi/login` — web login brute-force
- `POST /pwa/login` — mobile login brute-force
- All data-modifying endpoints — no protection against automated abuse

### 7.3 CORS

**No CORS headers are configured.** The application doesn't use Flask-CORS or set `Access-Control-Allow-*` headers. This means:

- Browser-based cross-origin requests will be blocked by the browser's same-origin policy
- API clients (curl, scripts) are unaffected
- If a reverse proxy adds permissive CORS headers, the API would be exposed

### 7.4 Content-Length Limiting

```python
app.config['MAX_CONTENT_LENGTH'] = config['app'].get('max_content_length', 10485760)  # 10 MB
```

A 10 MB upload limit is set. This is reasonable for receipt images and PDF attachments.

---

## 8. File Handling Security

### 8.1 File Upload

**Allowed extensions** are validated:
- Expense/invoice attachments: `{'pdf', 'png', 'jpg', 'jpeg'}`
- Logo uploads: `{'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}`

**Filename sanitization:** `werkzeug.utils.secure_filename()` is used consistently — good.

**Path construction:**
```python
filepath = os.path.join(upload_folder, f'{expense_id}_{filename}')
```

The `expense_id` is a UUID (validated), and `filename` is sanitized by `secure_filename()`. Path traversal risk is low.

**SVG uploads** for logos are a concern — SVG files can contain embedded JavaScript. If the SVG is served directly via `/uploads/<filename>` with `Content-Type: image/svg+xml`, the browser will execute any embedded scripts. This is a stored XSS vector.

### 8.2 File Download

```python
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(os.path.abspath(upload_folder), filename)
```

**This endpoint has NO authentication.** Anyone can download any file from the uploads directory if they know the filename. Filenames include UUIDs (`{expense_id}_{filename}`), which provides some obscurity, but the endpoint is still publicly accessible.

`send_from_directory` with an absolute path is safe against path traversal (it validates the path stays within the directory), but the lack of authentication is the issue.

### 8.3 PWA Image Processing

```python
image = Image.open(file)
if image.mode in ('RGBA', 'P'):
    image = image.convert('RGB')
image.save(filepath, 'JPEG', quality=85)
```

PIL/Pillow is used to re-encode uploaded images to JPEG. This strips any embedded payloads (EXIF, polyglot attacks) — good practice. However, Pillow itself has had vulnerabilities (CVE-2023-44271, etc.) — the dependency should be kept updated.

---

## 9. Logging & Error Handling

### 9.1 Sensitive Data in Logs

**Activity Log** (`activity_logs` table):
- Stores `old_values` and `new_values` as JSON
- For employee updates: uses `to_dict()` which returns **masked** PII — acceptable
- For user updates: uses `to_dict()` which includes **plaintext** `account_number` and `bsb` — **sensitive data in the audit log**
- IP addresses are logged — appropriate for audit purposes

**Application logs:**
- `current_app.logger.error(f'activity_log commit failed: {e}', exc_info=True)` — includes full traceback, could leak internal paths
- `current_app.logger.warning('Mail auth login failed for %s: %s', mail_user, auth_exc)` — logs the mail username (not password) — acceptable
- `print(f"Error fetching exchange rate: {e}")` — uses `print()` instead of proper logging — inconsistent

### 9.2 Error Handling

**Information leakage in error responses:**
- `return jsonify({'error': f'Database error: {str(e)}'}), 500` — leaks internal database error messages to the client
- `return jsonify({'error': f'PII encryption failed: {exc}'}), 500` — could leak encryption internals
- `return _err(f'PDF generation failed: {exc}', 500)` — could leak file system paths

**Inconsistent error handling:** Some endpoints use `abort(400, description=...)` (which returns HTML), while others return `jsonify({'error': ...}), 400`. This inconsistency could confuse API clients.

---

## 10. Secrets Management

### 10.1 Environment Variables

Secrets are properly externalized to environment variables:

| Secret | Source | Default | Risk |
|--------|--------|---------|------|
| `SECRET_KEY` | Env var | `'dev-secret-key'` | **CRITICAL** — predictable default |
| `PAYROLL_PII_KEY` | Env var | None (fails fast) | Good |
| `DB_PASSWORD` | Env var | `''` | Medium — empty default |
| `MAIL_SERVER_PASSWORD` | Env var | `''` | Medium — empty default |
| `TWELVE_DATA_API_KEY` | Env var | None | Good |
| `DATABASE_URL` | Env var | Constructed from parts | Medium |

### 10.2 Hardcoded Secrets

No hardcoded secrets were found in the source code. The `.env.example` file properly documents all required secrets without including real values.

### 10.3 Configuration File

The application supports a YAML config file (`config.yaml`) that can contain database credentials:

```python
if config_path and os.path.exists(config_path):
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
```

`yaml.safe_load()` is used — good (prevents arbitrary code execution via YAML deserialization). However, if `config.yaml` contains plaintext database passwords, it must be protected with appropriate file permissions (600).

---

## 11. Findings

### F-01: Default Flask Secret Key — CRITICAL

**Severity:** Critical
**CWE:** CWE-798 (Use of Hard-coded Credentials)

**Description:** The Flask `SECRET_KEY` defaults to `'dev-secret-key'` if the `SECRET_KEY` environment variable is not set. Flask uses this key to sign session cookies. An attacker who knows the key can forge session cookies for any user, gaining full access to their account.

**Evidence:**
```python
# app/__init__.py, line 24
'secret_key': os.environ.get('SECRET_KEY', 'dev-secret-key'),

# app/__init__.py, line 41
app.config['SECRET_KEY'] = config['app'].get('secret_key', 'dev-secret-key')
```

The same default appears in `app/hmi/__init__.py` and `app/api/__init__.py`.

**Impact:** Full session hijacking for all users. Attacker can impersonate any user, access their financial data, modify invoices, view employee PII.

**Recommendation:**
1. Remove the default value entirely — fail to start if `SECRET_KEY` is not set
2. Add a startup check: `if app.config['SECRET_KEY'] == 'dev-secret-key': raise RuntimeError(...)`
3. Document key generation in deployment docs: `python3 -c "import secrets; print(secrets.token_hex(32))"`

---

### F-02: No CSRF Protection on HMI Forms — CRITICAL

**Severity:** Critical
**CWE:** CWE-352 (Cross-Site Request Forgery)

**Description:** None of the HMI (web UI) forms include CSRF tokens. All state-changing operations (create/update/delete expenses, invoices, employees, pay events, super payments, account categories, business details, logo upload, API key generation) are vulnerable to cross-site request forgery.

**Evidence:** No `Flask-WTF` or `CSRFProtect` middleware is configured. No `csrf_token` is generated or validated in any HMI route. One template (`payroll_pay_event_detail.html`) has a conditional CSRF token input:
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() if csrf_token is defined else '' }}">
```
But `csrf_token` is never defined — the condition always evaluates to an empty string.

**Impact:** An attacker can trick a logged-in user into visiting a malicious page that submits forged requests to the HMI. This could create/modify/delete financial records, change bank details, generate API keys, or terminate employees.

**Recommendation:**
1. Install and configure `Flask-WTF` with `CSRFProtect`
2. Add `{{ csrf_token() }}` to all HMI forms
3. Alternatively, implement a custom CSRF middleware using `secrets.compare_digest()`

---

### F-03: Open Registration — CRITICAL

**Severity:** Critical
**CWE:** CWE-284 (Improper Access Control)

**Description:** Both the API (`POST /api/auth/register`) and HMI (`GET/POST /register`) endpoints allow unrestricted account creation. Anyone who can reach the server can create an account and access the full application.

**Evidence:**
```python
# app/api/routes.py, line 83
@api_bp.route('/auth/register', methods=['POST'])
def register():
    # No invite code, no admin approval, no email verification gate
    user = User(email=email, country=country)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully', ...}), 201
```

**Impact:** In a multi-tenant deployment, unauthorized users can create accounts and access the application. Even in a single-tenant deployment, if the server is ever exposed to the network, anyone can register.

**Recommendation:**
1. Add an invite-code or admin-approval mechanism for registration
2. Alternatively, disable registration after the initial admin account is created
3. At minimum, require email verification before granting API access

---

### F-04: No Rate Limiting — CRITICAL

**Severity:** Critical
**CWE:** CWE-770 (Allocation of Resources Without Limits)

**Description:** No rate limiting is implemented on any endpoint. Authentication endpoints (login, register) are vulnerable to brute-force attacks. API endpoints are vulnerable to denial-of-service via request flooding.

**Evidence:** No `Flask-Limiter` or similar middleware is configured. No rate-limiting logic exists in any route handler.

**Impact:**
- Brute-force password attacks against `/api/auth/login` and `/hmi/login`
- Account enumeration via `/api/auth/register` (409 response reveals existing emails)
- DoS via expensive endpoints (PDF generation, Xero export, payroll summary)

**Recommendation:**
1. Install `Flask-Limiter`
2. Apply strict rate limits to auth endpoints: 5 requests/minute for login, 3/hour for register
3. Apply moderate rate limits to API endpoints: 100 requests/minute
4. Apply expensive-operation limits: 10/hour for PDF generation and exports

---

### F-05: User Bank Details Stored in Plaintext — HIGH

**Severity:** High
**CWE:** CWE-311 (Missing Encryption of Sensitive Data)

**Description:** The `User` model stores `account_number` and `bsb` (the business's bank account details) as plaintext VARCHAR columns. These values are returned in plaintext by `User.to_dict()`, which is used in API responses, activity logs, and PDF generation.

**Evidence:**
```python
# app/models/user.py, lines 39-40
account_number = db.Column(db.String(50), nullable=True)
bsb = db.Column(db.String(20), nullable=True)

# app/models/user.py, lines 82-83 (in to_dict)
'account_number': self.account_number,
'bsb': self.bsb,
```

**Impact:** Business bank account details are exposed in:
- API responses (`GET /api/auth/business`)
- Activity log entries (when business details are updated)
- Database backups (plaintext)
- Any log file that captures API responses

**Recommendation:**
1. Encrypt `account_number` and `bsb` using the same Fernet pattern as employee PII
2. Remove them from `to_dict()` or mask them (e.g., `*****678`)
3. Provide a separate `to_dict(include_sensitive=True)` for PDF generation

---

### F-06: Verification Token Displayed in Browser — HIGH

**Severity:** High
**CWE:** CWE-200 (Exposure of Sensitive Information)

**Description:** During HMI registration, the email verification token is displayed to the user via a flash message:

```python
# app/hmi/routes.py, lines 87-89
verification_url = url_for('hmi.verify_email', token=token, _external=True)
flash(f'Registration successful! Your verification token is: {token}', 'success')
flash(f'Please verify your email at: {verification_url}', 'info')
```

The full verification URL (including the token) is rendered in the browser. This token is also stored in the database as a plaintext VARCHAR(64).

**Impact:**
- The token is visible in the browser's page source, browser history, and any screenshots
- If the application is behind a shared computer or the page is cached, the token persists
- The token grants the ability to verify any email address without access to the email inbox

**Recommendation:**
1. Send the verification link via email (requires email sending capability)
2. If email is not available, display only a partial token and require the user to check their email
3. Add token expiry (e.g., 24 hours)
4. Rate-limit the verification endpoint

---

### F-07: Unauthenticated File Download Endpoint — HIGH

**Severity:** High
**CWE:** CWE-306 (Missing Authentication for Critical Function)

**Description:** The `/uploads/<path:filename>` endpoint serves files from the uploads directory without any authentication check.

**Evidence:**
```python
# app/__init__.py, lines 84-88
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    from flask import send_from_directory
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
    return send_from_directory(os.path.abspath(upload_folder), filename)
```

**Impact:** Anyone can download uploaded files (expense receipts, invoice attachments, logos, payslip PDFs) if they know or guess the filename. Payslip PDFs contain employee names, TFNs (masked), pay amounts, and bank references. Filenames include UUIDs, which provides some protection, but UUIDs may be leaked through other channels (API responses, activity logs).

**Recommendation:**
1. Add `@api_key_required` or `@login_required` to the `serve_upload` route
2. Verify the requesting user owns the file (check the associated expense/invoice/pay event)
3. Alternatively, serve files through a controlled endpoint that generates signed URLs with expiry

---

### F-08: No Session Cookie Security Flags — HIGH

**Severity:** High
**CWE:** CWE-1004 (Sensitive Cookie Without HttpOnly Flag), CWE-614 (Sensitive Cookie in HTTPS Session Without Secure Attribute)

**Description:** Flask session cookies are not configured with security flags. The application does not set `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, or `SESSION_COOKIE_SAMESITE`.

**Evidence:** No `SESSION_COOKIE_*` configuration anywhere in the codebase.

**Impact:**
- Without `Secure`: session cookies are transmitted over HTTP (if the app is ever accessed via HTTP)
- Without `SameSite`: session cookies are sent with cross-origin requests (CSRF risk amplifier)
- `HttpOnly` defaults to True in Flask 2.x, but should be explicitly set

**Recommendation:**
```python
app.config['SESSION_COOKIE_SECURE'] = True  # Requires HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
```

---

### F-09: SVG Logo Upload — Stored XSS Vector — HIGH

**Severity:** High
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

**Description:** The logo upload endpoint accepts SVG files. SVG is an XML-based format that can contain embedded JavaScript (`<script>` tags, `onload` attributes, etc.). If the SVG is served with `Content-Type: image/svg+xml` and rendered in a browser, the embedded scripts execute in the application's origin.

**Evidence:**
```python
# app/api/routes.py, line 1421
allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
```

**Impact:** Stored XSS in the application's origin. An attacker uploads a malicious SVG as their logo, then convinces another user to view it. The script executes with the victim's session, potentially stealing cookies or performing actions on their behalf.

**Recommendation:**
1. Remove `'svg'` from the allowed extensions for logo uploads
2. If SVG support is required, sanitize the SVG content server-side (e.g., with `defusedxml` or an SVG sanitizer)
3. Serve SVG files with `Content-Disposition: attachment` to prevent inline rendering
4. Add `Content-Security-Policy` headers to restrict script execution

---

### F-10: Customer Records Not User-Scoped (IDOR) — HIGH

**Severity:** High
**CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)

**Description:** Customer records are not scoped to the owning user. Any authenticated user can read, update, or delete any customer by ID. This is intentional per code comments ("customers are not user-scoped"), but it means User A can access User B's customer data.

**Evidence:**
```python
# app/api/routes.py, line 246-252
@api_bp.route('/customers/<customer_id>', methods=['GET'])
@api_key_required
def get_customer(customer_id):
    customer = Customer.query.get(customer_id)  # No user_id filter
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    return jsonify({'customer': customer.to_dict()}), 200
```

The same pattern applies to `PUT /api/customers/<id>`, `DELETE /api/customers/<id>`, and `GET /api/customers/<id>/statement.pdf`.

**Impact:** In a multi-tenant deployment, users can access each other's customer lists, contact details, and financial data. Customer statements of account (PDF) can be generated for any customer by any user.

**Recommendation:**
1. Add `user_id` column to the `customers` table
2. Filter all customer queries by `user_id`
3. If cross-user customer sharing is intentional, implement an explicit sharing/permission model

---

### F-11: No Password Complexity Requirements — MEDIUM

**Severity:** Medium
**CWE:** CWE-521 (Weak Password Requirements)

**Description:** The registration endpoint accepts any password without validation. Single-character passwords, common passwords, and passwords matching the email address are all accepted.

**Evidence:**
```python
# app/api/routes.py, lines 83-106
if not email or not password:
    return jsonify({'error': 'Email and password required'}), 400
# No further password validation
user.set_password(password)
```

**Recommendation:**
1. Enforce minimum 12-character passwords
2. Check against common password lists (e.g., `zxcvbn` library)
3. Require mixed case + digits for additional entropy

---

### F-12: Email Addresses Not Validated — MEDIUM

**Severity:** Medium
**CWE:** CWE-20 (Improper Input Validation)

**Description:** Email addresses are accepted without format validation. The `register` and `login` endpoints only check that the email field is non-empty.

**Evidence:**
```python
email = data.get('email', '').strip().lower()
if not email or not password:
    return jsonify({'error': 'Email and password required'}), 400
```

**Recommendation:** Use a proper email validation library (`email-validator` package) or at minimum a regex check.

---

### F-13: Database Error Messages Leaked to Clients — MEDIUM

**Severity:** Medium
**CWE:** CWE-209 (Generation of Error Message Containing Sensitive Information)

**Description:** Several endpoints return raw exception messages to the client:

```python
# app/api/bank_transactions.py
return jsonify({'error': f'Database error: {str(e)}'}), 500

# app/api/payroll.py
return _err(f'PII encryption failed: {exc}', 500)
return _err(f'PDF generation failed: {exc}', 500)
```

**Impact:** Internal error details (table names, column names, file paths, library versions) are exposed to API clients. This information aids attackers in crafting targeted attacks.

**Recommendation:** Return generic error messages to clients (`'Internal server error'`) and log the full exception server-side.

---

### F-14: No Email Verification Gate for API Access — MEDIUM

**Severity:** Medium
**CWE:** CWE-287 (Improper Authentication)

**Description:** The `POST /api/auth/api-key` endpoint requires authentication but does not check whether the user's email is verified. The HMI route (`/api-key/generate`) does check `user.email_verified`, but the API route does not.

**Evidence:**
```python
# app/api/routes.py, lines 130-137
@api_bp.route('/auth/api-key', methods=['POST'])
@api_key_required
def generate_api_key():
    user = request.current_user
    api_key = user.generate_api_key()
    # No email_verified check
```

**Impact:** A user who registers with a fake email can immediately generate an API key and use the full API.

**Recommendation:** Add `if not user.email_verified: return jsonify({'error': 'Email not verified'}), 403` before generating the API key.

---

### F-15: Payslip PDF Contains Full TFN — MEDIUM

**Severity:** Medium
**CWE:** CWE-359 (Exposure of Private Personal Information)

**Description:** The payslip PDF generator decrypts and includes the employee's full TFN in the generated PDF:

```python
# app/shared/pdf.py — generate_payslip_pdf()
tfn_plain = employee.tfn_plain if employee is not None else None
# ...
row('TFN', tfn_plain or '', 'Pay frequency', pay_event.pay_frequency),
```

**Impact:** Payslip PDFs stored on disk contain full TFNs. If the uploads directory is compromised (or the unauthenticated `/uploads/` endpoint is exploited), TFNs are exposed. Australian Privacy Act 1988 classifies TFNs as sensitive information requiring the highest level of protection.

**Recommendation:**
1. Consider masking the TFN on payslips (e.g., `*** *** 250`) — the employee knows their own TFN
2. If full TFN is legally required on payslips (Fair Work Act), ensure the PDF storage is encrypted at rest and access-controlled
3. Fix F-07 (unauthenticated file download) to prevent unauthorized access to payslip PDFs

---

### F-16: No Session Timeout — MEDIUM

**Severity:** Medium
**CWE:** CWE-613 (Insufficient Session Expiration)

**Description:** Flask sessions do not have a configured timeout. Once a user logs in, their session persists indefinitely (until the browser is closed or the cookie is manually cleared).

**Evidence:** No `PERMANENT_SESSION_LIFETIME` or session expiry logic is configured.

**Recommendation:**
```python
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
```

---

### F-17: Account Category Operations Not User-Scoped — MEDIUM

**Severity:** Medium
**CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)

**Description:** Account categories are global (not user-scoped). Any authenticated user can create, update, or delete account categories. This is likely intentional (shared chart of accounts), but the delete endpoint has no user-scoping or admin check.

**Evidence:**
```python
# app/api/routes.py, lines 212-238
@api_bp.route('/account-categories/<category_id>', methods=['DELETE'])
@api_key_required
def delete_account_category(category_id):
    category = AccountCategory.query.get(category_id)  # No user_id filter
    db.session.delete(category)
```

**Impact:** Any user can delete account categories that other users' expenses/invoices reference. The FK constraint (`ON DELETE SET NULL`) prevents data loss but orphans the records.

**Recommendation:** Add user-scoping to account categories, or restrict deletion to admin users.

---

### F-18: Mail Server Credentials Over HTTP — MEDIUM

**Severity:** Medium
**CWE:** CWE-319 (Cleartext Transmission of Sensitive Information)

**Description:** The payslip email sender authenticates with the mail server API over HTTP:

```python
# app/api/payroll.py
mail_api = _ca.config.get('MAIL_SERVER_API', os.environ.get('MAIL_SERVER_API', 'http://127.0.0.1:5003'))
auth_resp = requests.post(f'{mail_api}/auth/login', json={'email': mail_user, 'password': mail_pass}, timeout=10)
```

The mail server password is transmitted over HTTP. This is acceptable when the mail server is on localhost (`127.0.0.1`), but if the mail server is on a different host, the credentials are transmitted in cleartext.

**Recommendation:** Use HTTPS for the mail server API when it's not on localhost. Document this requirement in the deployment guide.

---

### F-19: No Content-Security-Policy Headers — LOW

**Severity:** Low
**CWE:** CWE-693 (Protection Mechanism Failure)

**Description:** No Content-Security-Policy headers are set on any response. This increases the impact of any XSS vulnerability.

**Recommendation:** Add CSP headers via Flask `after_request`:
```python
@app.after_request
def set_security_headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response
```

---

### F-20: No HSTS Headers — LOW

**Severity:** Low
**CWE:** CWE-319 (Cleartext Transmission of Sensitive Information)

**Description:** No HTTP Strict Transport Security (HSTS) headers are set. If the application is deployed behind HTTPS, browsers won't be instructed to always use HTTPS.

**Recommendation:** Add HSTS header when deployed behind HTTPS:
```python
response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
```

---

### F-21: Dependency Versions Not Pinned — LOW

**Severity:** Low
**CWE:** CWE-1104 (Use of Unmaintained Third Party Components)

**Description:** `requirements.txt` uses minimum version constraints (`>=`) rather than pinned versions (`==`). This means builds are not reproducible and could pull in vulnerable versions.

**Evidence:**
```
flask>=2.3.0
werkzeug>=2.3.0
pillow>=9.5.0
```

**Recommendation:** Pin exact versions and use `pip-audit` or `safety` to check for known vulnerabilities:
```
flask==3.1.2
werkzeug==3.1.3
pillow==11.3.0
```

---

### F-22: Pillow Image Processing — Known Vulnerability History — LOW

**Severity:** Low
**CWE:** CWE-1104 (Use of Unmaintained Third Party Components)

**Description:** Pillow is used to process uploaded images in the PWA route. Pillow has a history of vulnerabilities related to malformed image processing (CVE-2023-44271, CVE-2023-50447, etc.).

**Recommendation:** Keep Pillow updated to the latest version. Consider using `Pillow-SIMD` for performance with the same security posture. Add `pip-audit` to CI/CD.

---

### F-23: Activity Log IP Address May Be Inaccurate Behind Proxy — LOW

**Severity:** Low
**CWE:** CWE-348 (Use of Less Trusted Source)

**Description:** `request.remote_addr` is used for activity logging. If the application is behind a reverse proxy (nginx, Caddy), `remote_addr` will be the proxy's IP, not the client's.

**Recommendation:** Use `ProxyFix` middleware:
```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
```

---

### F-24: `print()` Used for Error Logging — INFORMATIONAL

**Severity:** Informational

**Description:** `app/shared/currency.py` uses `print()` for error logging instead of the standard `logging` module:
```python
print(f"Error fetching exchange rate: {e}")
```

**Recommendation:** Use `current_app.logger.error()` or the `logging` module for consistent log management.

---

### F-25: No Database Connection Encryption — INFORMATIONAL

**Severity:** Informational

**Description:** The PostgreSQL connection string does not specify `sslmode`. If the database is on the same host (localhost), this is acceptable. If remote, the connection is unencrypted.

**Recommendation:** Add `?sslmode=require` to the `DATABASE_URL` when connecting to a remote PostgreSQL instance.

---

### F-26: No Backup Encryption Mentioned — INFORMATIONAL

**Severity:** Informational

**Description:** The application stores sensitive financial data and encrypted PII in PostgreSQL. Database backups should be encrypted at rest.

**Recommendation:** Document backup encryption requirements in the deployment guide. Use `pg_dump` with encryption or encrypted filesystem for backups.

---

## 12. Deployment Security Checklist

### Pre-Deployment (Must Complete)

- [ ] Set `SECRET_KEY` to a cryptographically random 64-char hex string
- [ ] Set `PAYROLL_PII_KEY` to a valid Fernet key
- [ ] Set `DB_PASSWORD` to a strong password
- [ ] Configure HTTPS via reverse proxy (nginx/Caddy/Traefik)
- [ ] Set `SESSION_COOKIE_SECURE = True`
- [ ] Set `SESSION_COOKIE_HTTPONLY = True`
- [ ] Set `SESSION_COOKIE_SAMESITE = 'Lax'`
- [ ] Install and configure CSRF protection (Flask-WTF)
- [ ] Install and configure rate limiting (Flask-Limiter)
- [ ] Disable or restrict open registration
- [ ] Add authentication to `/uploads/<filename>` endpoint
- [ ] Remove SVG from allowed logo upload extensions
- [ ] Pin all dependency versions in requirements.txt
- [ ] Run `pip-audit` to check for known vulnerabilities

### Post-Deployment (Recommended)

- [ ] Configure `ProxyFix` middleware for accurate IP logging
- [ ] Set up HSTS headers at the reverse proxy level
- [ ] Configure Content-Security-Policy headers
- [ ] Set up database backup encryption
- [ ] Configure PostgreSQL SSL (`sslmode=require`)
- [ ] Set up log rotation and monitoring
- [ ] Implement email-based verification (replace flash-message tokens)
- [ ] Add account lockout after N failed login attempts
- [ ] Review and restrict network access (bind to localhost, firewall rules)
- [ ] Set up automated security updates for the OS and dependencies

---

## 13. Recommended Priority Fixes

### Immediate (This Week)

1. **F-01: Remove default SECRET_KEY** — one-line change, prevents session forgery
2. **F-02: Add CSRF protection** — install Flask-WTF, add tokens to all forms
3. **F-04: Add rate limiting** — install Flask-Limiter, protect auth endpoints
4. **F-03: Restrict registration** — add invite code or disable after first user

### Short-term (This Sprint)

5. **F-05: Encrypt User bank details** — apply Fernet pattern to `User.account_number` and `User.bsb`
6. **F-07: Authenticate file downloads** — add auth check to `/uploads/` endpoint
7. **F-08: Set session cookie flags** — 4 lines of config
8. **F-09: Remove SVG upload support** — one-line change to allowed extensions

### Medium-term (This Month)

9. **F-10: User-scope customer records** — add `user_id` to Customer model
10. **F-06: Implement email verification** — replace flash-message tokens with emailed links
11. **F-11/F-12: Add password + email validation** — use `email-validator` and `zxcvbn`
12. **F-13: Sanitize error messages** — generic client errors, detailed server logs
13. **F-14: Gate API key generation on email verification**

### Long-term (This Quarter)

14. **F-15: Evaluate TFN masking on payslips** — legal review required
15. **F-21/F-22: Pin dependencies + add vulnerability scanning** — CI/CD integration
16. **Implement RBAC** — admin/user roles for multi-tenant deployments
17. **Key rotation for PAYROLL_PII_KEY** — plan for periodic key rotation with re-encryption
18. **KMS upgrade for PII** — migrate from in-process Fernet to a separate decryption daemon (as documented in `app/shared/pii.py` Phase 5)

---

*End of audit report.*
