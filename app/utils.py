import re
from flask import current_app
from app.models import UserComplex

def clean_text(text, max_length=None):
    """Clean and sanitize text input"""
    if not text:
        return ""
    
    # Remove HTML tags and normalize whitespace
    text = re.sub(r'<[^>]+>', '', str(text))
    text = re.sub(r'\s+', ' ', text).strip()
    
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text

def user_can_manage_complex(user_id, complex_id):
    """Check if user can manage a specific complex"""
    if not user_id or not complex_id:
        return False
    
    from app.models import AppUser
    user = AppUser.query.get(user_id)
    
    if not user:
        return False
    
    # Superadmin can manage all complexes
    if user.is_superadmin:
        return True
    
    # Check if user is linked to this complex
    user_complex = UserComplex.query.filter_by(
        user_id=user_id,
        complex_id=complex_id
    ).first()
    
    return user_complex is not None

def validate_date_format(date_str):
    """Validate date format YYYY-MM-DD"""
    if not date_str:
        return False
    
    pattern = r'^\d{4}-\d{2}-\d{2}$'
    return bool(re.match(pattern, date_str))

def validate_email(email):
    """Validate email format"""
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

ALLOWED_CATEGORIES = ['deportes', 'estetica', 'profesionales']
ALLOWED_SPANS = ['day', 'week']
ALLOWED_STATUSES = ['available', 'holding', 'reserved', 'blocked']
ALLOWED_ORDER_BY = ['start', 'price', 'created_at']

def validate_category(category):
    """Validate category against allow-list"""
    return category in ALLOWED_CATEGORIES

def validate_span(span):
    """Validate span against allow-list"""
    return span in ALLOWED_SPANS

def validate_status(status):
    """Validate status against allow-list"""
    return status in ALLOWED_STATUSES

def validate_order_by(order_by):
    """Validate order_by against allow-list"""
    return order_by in ALLOWED_ORDER_BY
