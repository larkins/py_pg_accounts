from flask import Flask
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
    app.config['SECRET_KEY'] = config['app'].get('secret_key', 'dev-secret-key')
    app.config['UPLOAD_FOLDER'] = config['app'].get('upload_folder', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = config['app'].get('max_content_length', 10485760)

    app.config['VISION_OLLAMA_HOST'] = config.get('vision', {}).get('ollama_host', 'http://localhost:11434')
    app.config['VISION_MODEL'] = config.get('vision', {}).get('model', 'gemma4:31b')
    app.config['VISION_TIMEOUT'] = config.get('vision', {}).get('timeout', 2100.0)

    db.init_app(app)

    from app.api.routes import api_bp
    from app.api.reports import reports_bp
    from app.api.payroll import payroll_api_bp
    from app.api.bas import bas_bp
    from app.hmi.routes import hmi_bp
    from app.hmi.payroll import payroll_hmi_bp
    from app.pwa.routes import pwa_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(payroll_api_bp)
    app.register_blueprint(bas_bp)
    app.register_blueprint(hmi_bp)
    app.register_blueprint(payroll_hmi_bp)
    app.register_blueprint(pwa_bp)

    @app.route('/health')
    def health():
        from datetime import datetime, timezone
        return {'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()}

    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        from flask import send_from_directory
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        return send_from_directory(os.path.abspath(upload_folder), filename)

    return app
