from functools import wraps
from flask import request, jsonify, current_app, session
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
    text = re.sub(r'[<>"\']', '', str(text))
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
    """Add security headers to response"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
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
