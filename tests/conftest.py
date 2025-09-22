import pytest
import tempfile
import os
from app import create_app, db
from app.models import AppUser, Complex, Category, Service, Field, Timeslot
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
        user = AppUser(
            email='admin@test.com',
            name='Test Admin',
            is_super_admin=False
        )
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
        return user

@pytest.fixture
def super_admin_user(app):
    """Create super admin user for testing"""
    with app.app_context():
        user = AppUser(
            email='superadmin@test.com',
            name='Test Super Admin',
            is_super_admin=True
        )
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
        return user

@pytest.fixture
def sample_data(app):
    """Create sample data for testing"""
    with app.app_context():
        # Create category
        category = Category(name='deportes', display_name='Deportes')
        db.session.add(category)
        
        # Create complex
        complex_obj = Complex(
            name='Test Complex',
            address='Test Address',
            phone='123456789',
            email='complex@test.com'
        )
        db.session.add(complex_obj)
        
        # Create service
        service = Service(
            name='Test Service',
            category=category,
            complex=complex_obj
        )
        db.session.add(service)
        
        # Create field
        field = Field(
            name='Test Field',
            service=service
        )
        db.session.add(field)
        
        db.session.commit()
        
        # Create timeslot
        timeslot = Timeslot(
            field=field,
            start_time=datetime.now() + timedelta(days=1),
            end_time=datetime.now() + timedelta(days=1, hours=1),
            price=50.0,
            status='available'
        )
        db.session.add(timeslot)
        db.session.commit()
        
        return {
            'category': category,
            'complex': complex_obj,
            'service': service,
            'field': field,
            'timeslot': timeslot
        }
