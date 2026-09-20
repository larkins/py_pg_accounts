"""In-memory rate limiter for auth endpoints.

Single-process Flask app, so in-memory is sufficient. Tracks failed
login attempts per IP and locks out after repeated failures.

Limits:
  - 5 failed attempts per IP per 15-minute window → 15-minute lockout
  - Successful login resets the counter
"""

import time
import threading
from collections import defaultdict
from functools import wraps

from flask import request, jsonify, flash, render_template

_lock = threading.Lock()

# {ip: [(timestamp, success), ...]}
_attempts: dict[str, list[tuple[float, bool]]] = defaultdict(list)

# {ip: lockout_until_timestamp}
_lockouts: dict[str, float] = {}

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60       # 15 minutes
LOCKOUT_SECONDS = 15 * 60      # 15 minutes


def _get_client_ip() -> str:
    """Get the real client IP, respecting proxy headers."""
    return (
        request.headers.get('CF-Connecting-IP')
        or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        or request.remote_addr
        or 'unknown'
    )


def _cleanup_old_attempts(ip: str, now: float):
    cutoff = now - WINDOW_SECONDS
    _attempts[ip] = [(ts, ok) for ts, ok in _attempts[ip] if ts > cutoff]


def is_locked_out(ip: str) -> bool:
    with _lock:
        until = _lockouts.get(ip, 0)
        if until > time.time():
            return True
        if ip in _lockouts:
            del _lockouts[ip]
        return False


def record_attempt(ip: str, success: bool):
    now = time.time()
    with _lock:
        if success:
            _attempts.pop(ip, None)
            _lockouts.pop(ip, None)
            return

        _cleanup_old_attempts(ip, now)
        _attempts[ip].append((now, False))

        failed = sum(1 for _, ok in _attempts[ip] if not ok)
        if failed >= MAX_ATTEMPTS:
            _lockouts[ip] = now + LOCKOUT_SECONDS
            _attempts.pop(ip, None)


def remaining_lockout_seconds(ip: str) -> int:
    with _lock:
        until = _lockouts.get(ip, 0)
        remaining = until - time.time()
        return max(0, int(remaining))


def rate_limit_api(f):
    """Rate-limit decorator for API auth endpoints (returns JSON 429)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        ip = _get_client_ip()
        if is_locked_out(ip):
            secs = remaining_lockout_seconds(ip)
            return jsonify({
                'error': f'Too many failed attempts. Try again in {secs // 60 + 1} minutes.'
            }), 429
        return f(*args, **kwargs)
    return wrapper


def rate_limit_hmi(template_name):
    """Rate-limit decorator for HMI auth endpoints (renders template with flash)."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if request.method == 'POST':
                ip = _get_client_ip()
                if is_locked_out(ip):
                    secs = remaining_lockout_seconds(ip)
                    mins = secs // 60 + 1
                    flash(
                        f'Too many failed login attempts. Try again in {mins} minute{"s" if mins != 1 else ""}.',
                        'error',
                    )
                    return render_template(template_name), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator
