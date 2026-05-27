from functools import wraps
from flask import request, jsonify

from app.models import db
from app.models.user import User
from app.models.activity_log import ActivityLog


def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401

        user = User.query.filter_by(api_key=api_key).first()
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401

        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def log_activity(user_id, action, table_name, record_id, old_values=None, new_values=None, ip_address=None):
    log = ActivityLog(
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address
    )
    db.session.add(log)
    return log
