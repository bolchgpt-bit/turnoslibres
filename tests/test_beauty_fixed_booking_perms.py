from app import db
from app.models import Category
from app.models_catalog import BeautyCenter


def test_only_superadmin_can_change_fixed_mode(app, client, admin_user):
    with app.app_context():
        # Prepare estetica category and assign to admin_user
        cat = Category(slug='estetica', title='Estética')
        db.session.add(cat)
        db.session.flush()
        # Assign category to admin
        admin_user.category_id = cat.id
        db.session.add(admin_user)
        db.session.flush()

        center = BeautyCenter(name='Centro A', slug='centro-a', city='CABA', category_id=cat.id)
        db.session.add(center)
        db.session.commit()

        # Login as regular admin
        client.post('/admin/login', data={'email': 'admin@test.com', 'password': 'testpass123'})

        # Try to set fixed mode via settings (should not change)
        resp = client.post('/admin/beauty_settings/update', data={
            'center_id': center.id,
            'show_public_booking': '1',
            'booking_mode': 'fixed',
        })
        assert resp.status_code in (200, 302)

        # Reload and verify mode remains default flexible
        db.session.refresh(center)
        assert getattr(center, 'booking_mode', 'flexible') == 'flexible'

