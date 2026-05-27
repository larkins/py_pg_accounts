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
            }
        }

    db_url = f"postgresql://{config['database']['user']}@{config['database']['host']}:{config['database']['port']}/{config['database']['name']}"
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = config['app'].get('secret_key', 'dev-secret-key')
    app.config['UPLOAD_FOLDER'] = config['app'].get('upload_folder', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = config['app'].get('max_content_length', 10485760)

    db.init_app(app)

    from app.api.routes import api_bp
    from app.api.reports import reports_bp
    from app.hmi.routes import hmi_bp
    from app.pwa.routes import pwa_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(hmi_bp)
    app.register_blueprint(pwa_bp)

    @app.route('/health')
    def health():
        from datetime import datetime, timezone
        return {'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()}

    return app
