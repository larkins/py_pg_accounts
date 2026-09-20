from flask import Flask
from flask_wtf.csrf import CSRFProtect
import yaml
import os

from app.models import db


def create_app(config_path=None):
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'hmi', 'templates')
    app = Flask(__name__, template_folder=template_dir)

    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        config = {
            'database': {
                'host': os.environ.get('DB_HOST', 'localhost'),
                'port': os.environ.get('DB_PORT', '5432'),
                'name': os.environ.get('DB_NAME', 'py_pg_accounts'),
                'user': os.environ.get('DB_USER', 'postgres')
            },
            'app': {
                'secret_key': os.environ.get('SECRET_KEY', 'dev-secret-key'),
                'upload_folder': os.environ.get('UPLOAD_FOLDER', 'uploads'),
                'max_content_length': 10485760
            },
            'vision': {
                'ollama_host': os.environ.get('DEFAULT_LOCAL_VISION_OLLAMA_HOST', 'http://localhost:11434'),
                'model': os.environ.get('DEFAULT_LOCAL_VISION_MODEL', 'gemma4:31b'),
                'timeout': float(os.environ.get('DEFAULT_LOCAL_VISION_TIMEOUT', 2100.0))
            }
        }

    if 'database' in config and 'password' in config['database']:
        db_url = f"postgresql://{config['database']['user']}:{config['database']['password']}@{config['database']['host']}:{config['database']['port']}/{config['database']['name']}"
    else:
        db_url = f"postgresql://{os.environ.get('DB_USER', 'postgres')}:{os.environ.get('DB_PASSWORD', '')}@{os.environ.get('DB_HOST', 'localhost')}:{os.environ.get('DB_PORT', '5432')}/{os.environ.get('DB_NAME', 'py_pg_accounts')}"
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # SECRET_KEY: no default — fail to start without it
    secret_key = config['app'].get('secret_key') or os.environ.get('SECRET_KEY')
    if not secret_key or secret_key == 'dev-secret-key':
        raise RuntimeError(
            'SECRET_KEY environment variable is required. '
            'Set it in .env or config.yaml. Do not use the default.'
        )
    app.config['SECRET_KEY'] = secret_key
    
    app.config['UPLOAD_FOLDER'] = config['app'].get('upload_folder', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = config['app'].get('max_content_length', 10485760)

    # Session cookie security
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

    app.config['VISION_OLLAMA_HOST'] = config.get('vision', {}).get('ollama_host', 'http://localhost:11434')
    app.config['VISION_MODEL'] = config.get('vision', {}).get('model', 'gemma4:31b')
    app.config['VISION_TIMEOUT'] = config.get('vision', {}).get('timeout', 2100.0)

    db.init_app(app)

    from app.api.routes import api_bp
    from app.api.reports import reports_bp
    from app.api.payroll import payroll_api_bp
    from app.api.bas import bas_bp
    from app.api.bank_transactions import bank_txn_bp
    from app.api.invoice_reminders import invoice_reminders_bp
    from app.api.payment_reconciliations import payment_recon_bp
    from app.api.xero_export import xero_export_bp
    from app.api.payroll_exports import payroll_exports_bp
    from app.api.settings import settings_bp
    from app.hmi.routes import hmi_bp
    from app.hmi.payroll import payroll_hmi_bp
    from app.pwa.routes import pwa_bp

    # CSRF protection for HMI/PWA forms (cookie-based auth)
    # API blueprints are exempt — they use X-API-Key header auth, not cookies
    csrf = CSRFProtect(app)
    for bp in (api_bp, reports_bp, payroll_api_bp, bas_bp, bank_txn_bp,
               invoice_reminders_bp, payment_recon_bp, xero_export_bp,
               payroll_exports_bp, settings_bp):
        csrf.exempt(bp)

    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(payroll_api_bp)
    app.register_blueprint(bas_bp)
    app.register_blueprint(bank_txn_bp)
    app.register_blueprint(invoice_reminders_bp)
    app.register_blueprint(payment_recon_bp)
    app.register_blueprint(xero_export_bp)
    app.register_blueprint(payroll_exports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(hmi_bp)
    app.register_blueprint(payroll_hmi_bp)
    app.register_blueprint(pwa_bp)

    @app.route('/health')
    def health():
        from datetime import datetime, timezone
        return {'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()}

    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        from flask import send_from_directory, session, abort
        from app.shared.decorators import _resolve_current_user
        # Require authentication — receipts and logos contain sensitive data.
        # Accepts both session cookie (HMI <img> tags) and X-API-Key header.
        user = _resolve_current_user()
        if not user:
            abort(401)
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        return send_from_directory(os.path.abspath(upload_folder), filename)

    # Seed the system_settings table with default business constants
    # (BUSINESS_NAME, DEFAULT_FUND_ABN, etc.) on first boot. Idempotent —
    # only inserts missing keys, never overwrites values an admin has
    # already set via PUT /api/settings/<key>.
    with app.app_context():
        from app.models.system_setting import seed_defaults
        seed_defaults(app)

    return app
