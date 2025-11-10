import pytest
import tempfile
import os
from app import create_app, db
from app.models import AppUser
from datetime import datetime, timedelta, timezone

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
    
@pytest.fixture
def sample_data(app):
    from app import db
    from app.models import Category, Complex, Field, Timeslot, TimeslotStatus
    from datetime import datetime, timedelta, timezone
    with app.app_context():
        cat = Category(slug='deportes', title='Deportes')
        db.session.add(cat); db.session.flush()
        cpx = Complex(name='Complejo Test', slug='complejo-test', city='X', show_public_booking=True)
        db.session.add(cpx); db.session.flush()
        fld = Field(complex_id=cpx.id, name='Cancha 1', sport='futbol', is_active=True, show_public_booking=True)
        db.session.add(fld); db.session.flush()
        now = datetime.now(timezone.utc)
        ts = Timeslot(field_id=fld.id, start=now + timedelta(hours=2), end=now + timedelta(hours=3), status=TimeslotStatus.AVAILABLE)
        db.session.add(ts); db.session.commit()
        return {'category': cat, 'complex': cpx, 'field': fld, 'timeslot': ts}