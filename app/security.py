from functools import wraps
from flask import request, jsonify, current_app, session, abort
from flask_login import current_user
from flask_limiter.util import get_remote_address
import time
import hashlib
import hmac
from datetime import datetime, timedelta
import re

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Validate phone format (basic validation)"""
    if not phone:
        return True  # Phone is optional
    pattern = r'^\+?[\d\s\-$$$$]{8,15}$'
    return re.match(pattern, phone) is not None

def sanitize_input(text, max_length=255):
    """Sanitize text input"""
    if not text:
        return ""
    # Remove potentially dangerous characters
    text = re.sub(r'[<>]', '', str(text))
    # Remove quotes unless they are wrapped by parentheses e.g., ("safe")
    text = re.sub(r'(?<!\()"(?!\))', '', text)
    return text[:max_length].strip()

def generate_csrf_token():
    """Generate CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = hashlib.sha256(
            f"{time.time()}{current_app.secret_key}".encode()
        ).hexdigest()
    return session['csrf_token']

def validate_csrf_token(token):
    """Validate CSRF token"""
    return token and session.get('csrf_token') == token

def honeypot_check(form_data):
    """Check for honeypot field (should be empty)"""
    return form_data.get('website', '') == ''

def rate_limit_key():
    """Generate rate limit key based on IP and user"""
    ip = get_remote_address()
    user_id = session.get('user_id', 'anonymous')
    return f"{ip}:{user_id}"

def security_headers(response):
    """Add security headers to response in an idempotent way.

    - Only set headers if they are not already present (to avoid duplicates when
      running behind a reverse proxy like Nginx that may set the same headers).
    - Set HSTS only for secure requests to avoid confusing behavior on HTTP.
    """

    # If we are behind a reverse proxy (e.g., Nginx sets X-Forwarded-Proto),
    # let the proxy be the single source of truth for security headers to avoid
    # duplicated header entries observed by clients.
    behind_proxy = bool(request.headers.get('X-Forwarded-Proto'))
    if behind_proxy:
        return response

    def _set_if_absent(key: str, value: str) -> None:
        if not response.headers.get(key):
            response.headers[key] = value

    _set_if_absent('X-Content-Type-Options', 'nosniff')
    _set_if_absent('X-Frame-Options', 'DENY')
    _set_if_absent('X-XSS-Protection', '1; mode=block')

    # Only set HSTS when the request is secure. Many deployments terminate TLS
    # at the proxy, which should set HSTS at the edge (Nginx). This keeps dev
    # and proxy setups from getting duplicate/conflicting headers.
    try:
        is_secure = bool(getattr(request, 'is_secure', False)) or (
            request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
        )
    except Exception:
        is_secure = False
    if is_secure:
        _set_if_absent('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

    # Content Security Policy: set a safe default for dev/standalone runs, but
    # avoid overriding if already provided by the proxy.
    if not response.headers.get('Content-Security-Policy'):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self';"
        )

    return response

def validate_subscription_criteria(criteria):
    """Validate subscription criteria"""
    allowed_keys = {'category', 'complex_id', 'service_id', 'field_id', 'date_from', 'date_to', 'time_from', 'time_to', 'max_price'}
    
    if not isinstance(criteria, dict):
        return False
    
    # Check for allowed keys only
    if not all(key in allowed_keys for key in criteria.keys()):
        return False
    
    # Validate date formats
    date_fields = ['date_from', 'date_to']
    for field in date_fields:
        if field in criteria:
            try:
                datetime.strptime(criteria[field], '%Y-%m-%d')
            except ValueError:
                return False
    
    # Validate time formats
    time_fields = ['time_from', 'time_to']
    for field in time_fields:
        if field in criteria:
            try:
                datetime.strptime(criteria[field], '%H:%M')
            except ValueError:
                return False
    
    # Validate numeric fields
    if 'max_price' in criteria:
        try:
            float(criteria['max_price'])
        except (ValueError, TypeError):
            return False
    
    return True

def log_security_event(event_type, details, user_id=None):
    """Log security events"""
    timestamp = datetime.utcnow().isoformat()
    ip = get_remote_address()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    log_entry = {
        'timestamp': timestamp,
        'event_type': event_type,
        'ip': ip,
        'user_id': user_id,
        'user_agent': user_agent,
        'details': details
    }
    
    current_app.logger.warning(f"SECURITY_EVENT: {log_entry}")


def superadmin_required(view_func):
    """Decorator to ensure the current user is superadmin.

    - For HTMX or JSON requests returns a 403 JSON payload.
    - For regular requests aborts with 403.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        try:
            is_super = bool(getattr(current_user, 'is_superadmin', False))
        except Exception:
            is_super = False
        if not is_super:
            if request.headers.get('HX-Request') or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'error': 'Unauthorized'}), 403
            return abort(403)
        return view_func(*args, **kwargs)
    return wrapped
