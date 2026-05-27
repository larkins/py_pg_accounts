from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

def get_utc_now():
    return datetime.now(timezone.utc)
