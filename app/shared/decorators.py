from functools import wraps
from flask import request, session, jsonify

from app.models import db
from app.models.user import User
from app.models.activity_log import ActivityLog


def _resolve_current_user():
    """Resolve the calling user via either X-API-Key or session cookie.

    Returns the User row, or None if neither auth method succeeded.
    """
    # 1. Try X-API-Key header (programmatic API clients)
    api_key = request.headers.get('X-API-Key')
    if api_key:
        user = User.query.filter_by(api_key=api_key).first()
        if user:
            return user
        # An API key was provided but didn't match — don't silently fall
        # through to session auth, since that would let a typo'd key pass
        # via cookie. Reject explicitly.
        return None

    # 2. Try session cookie (HMI users logged in via the web UI)
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None


def api_key_required(f):
    """Auth decorator that accepts either:
      - X-API-Key header (programmatic API clients — cron jobs, scripts)
      - Flask session cookie (HMI users — the web UI session)

    The route body uses `request.current_user` to identify the caller, so
    this is transparent to the underlying handler.

    Returns 401 with a clear error if neither method authenticated the
    request.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = _resolve_current_user()
        if not user:
            # Distinguish between the two failure modes for easier
            # debugging. A bare HTTP client (no cookies, no API key)
            # gets the 'API key required' message; a logged-in HMI user
            # shouldn't ever see this — if they do, the session cookie
            # has expired.
            if 'user_id' in session:
                # Logged-in user but session lookup failed (user deleted?)
                return jsonify({'error': 'Session expired or user not found'}), 401
            return jsonify({'error': 'API key required (or HMI session login)'}), 401

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
