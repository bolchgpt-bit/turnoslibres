import pytest
from app.security import (
    validate_email, validate_phone, sanitize_input,
    validate_subscription_criteria, honeypot_check
)

def test_validate_email():
    """Test email validation"""
    assert validate_email('user@example.com') is True
    assert validate_email('invalid-email') is False
    assert validate_email('user@') is False
    assert validate_email('@example.com') is False

def test_validate_phone():
    """Test phone validation"""
    assert validate_phone('+1234567890') is True
    assert validate_phone('123-456-7890') is True
    assert validate_phone('123') is False
    assert validate_phone('') is True  # Optional field

def test_sanitize_input():
    """Test input sanitization"""
    assert sanitize_input('<script>alert("xss")</script>') == 'scriptalert("xss")/script'
    assert sanitize_input('Normal text') == 'Normal text'
    assert sanitize_input('Text with "quotes"') == 'Text with quotes'

def test_validate_subscription_criteria():
    """Test subscription criteria validation"""
    valid_criteria = {
        'category': 'deportes',
        'max_price': 100.0,
        'date_from': '2024-01-01',
        'time_from': '10:00'
    }
    assert validate_subscription_criteria(valid_criteria) is True
    
    invalid_criteria = {
        'invalid_key': 'value'
    }
    assert validate_subscription_criteria(invalid_criteria) is False
    
    invalid_date = {
        'date_from': 'invalid-date'
    }
    assert validate_subscription_criteria(invalid_date) is False

def test_honeypot_check():
    """Test honeypot spam protection"""
    clean_form = {'email': 'user@test.com', 'website': ''}
    spam_form = {'email': 'user@test.com', 'website': 'spam-content'}
    
    assert honeypot_check(clean_form) is True
    assert honeypot_check(spam_form) is False
