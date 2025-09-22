import pytest
from app.models import AppUser
from app import db

def test_register_valid_user(client):
    """Test user registration with valid data"""
    response = client.post('/admin/register', data={
        'email': 'newuser@test.com',
        'name': 'New User',
        'password': 'testpass123',
        'confirm_password': 'testpass123'
    })
    assert response.status_code == 302  # Redirect after successful registration

def test_register_duplicate_email(client, admin_user):
    """Test registration with duplicate email"""
    response = client.post('/admin/register', data={
        'email': 'admin@test.com',  # Same as admin_user
        'name': 'Another User',
        'password': 'testpass123',
        'confirm_password': 'testpass123'
    })
    assert b'Email already registered' in response.data

def test_login_valid_credentials(client, admin_user):
    """Test login with valid credentials"""
    response = client.post('/admin/login', data={
        'email': 'admin@test.com',
        'password': 'testpass123'
    })
    assert response.status_code == 302  # Redirect after successful login

def test_login_invalid_credentials(client, admin_user):
    """Test login with invalid credentials"""
    response = client.post('/admin/login', data={
        'email': 'admin@test.com',
        'password': 'wrongpassword'
    })
    assert b'Invalid email or password' in response.data

def test_logout(client, admin_user):
    """Test user logout"""
    # Login first
    client.post('/admin/login', data={
        'email': 'admin@test.com',
        'password': 'testpass123'
    })
    
    # Then logout
    response = client.get('/admin/logout')
    assert response.status_code == 302  # Redirect after logout

def test_admin_panel_requires_login(client):
    """Test that admin panel requires authentication"""
    response = client.get('/admin/panel')
    assert response.status_code == 302  # Redirect to login

def test_super_admin_panel_requires_super_admin(client, admin_user):
    """Test that super admin panel requires super admin role"""
    # Login as regular admin
    client.post('/admin/login', data={
        'email': 'admin@test.com',
        'password': 'testpass123'
    })
    
    response = client.get('/admin/super')
    assert response.status_code == 403  # Forbidden
