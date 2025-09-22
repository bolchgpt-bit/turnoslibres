import pytest
from app.models import AppUser, Complex, Category, Service, Field, Timeslot, Subscription
from app import db
from datetime import datetime, timedelta

def test_user_password_hashing():
    """Test user password hashing and verification"""
    user = AppUser(email='test@example.com', name='Test User')
    user.set_password('testpassword')
    
    assert user.password_hash is not None
    assert user.password_hash != 'testpassword'
    assert user.check_password('testpassword') is True
    assert user.check_password('wrongpassword') is False

def test_user_repr():
    """Test user string representation"""
    user = AppUser(email='test@example.com', name='Test User')
    assert repr(user) == '<AppUser test@example.com>'

def test_complex_model(app):
    """Test complex model creation"""
    with app.app_context():
        complex_obj = Complex(
            name='Test Complex',
            address='Test Address',
            phone='123456789',
            email='complex@test.com'
        )
        db.session.add(complex_obj)
        db.session.commit()
        
        assert complex_obj.id is not None
        assert complex_obj.name == 'Test Complex'

def test_timeslot_availability(app, sample_data):
    """Test timeslot availability logic"""
    with app.app_context():
        timeslot = sample_data['timeslot']
        
        # Initially available
        assert timeslot.status == 'available'
        
        # Mark as reserved
        timeslot.status = 'reserved'
        db.session.commit()
        
        assert timeslot.status == 'reserved'

def test_subscription_model(app, sample_data):
    """Test subscription model"""
    with app.app_context():
        subscription = Subscription(
            email='user@test.com',
            timeslot_id=sample_data['timeslot'].id
        )
        db.session.add(subscription)
        db.session.commit()
        
        assert subscription.id is not None
        assert subscription.email == 'user@test.com'
        assert subscription.is_active is True
