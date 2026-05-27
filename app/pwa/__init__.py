from flask import Flask

def create_pwa_app():
    app = Flask(__name__, template_folder='templates')

    import os
    db_url = os.environ.get('DATABASE_URL', 'postgresql://postgres@localhost/py_pg_accounts')
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    from app.models import db
    db.init_app(app)

    from app.pwa.routes import pwa_bp
    app.register_blueprint(pwa_bp)

    return app
