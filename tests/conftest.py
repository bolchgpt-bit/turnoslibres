import pytest
import tempfile
import os
from app import create_app, db
from app.models import AppUser
from datetime import datetime, timedelta

@pytest.fixture
def app():
    """Create application for testing"""
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'REDIS_URL': 'redis://localhost:6379/1'  # Use different DB for tests
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()
    
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create test CLI runner"""
    return app.test_cli_runner()

@pytest.fixture
def admin_user(app):
    """Create admin user for testing"""
    with app.app_context():
        user = AppUser(email='admin@test.com', is_superadmin=False)
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
        return user

@pytest.fixture
def super_admin_user(app):
    """Create super admin user for testing"""
    with app.app_context():
        user = AppUser(email='superadmin@test.com', is_superadmin=True)
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
        return user
