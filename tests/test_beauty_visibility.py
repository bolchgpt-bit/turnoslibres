from app import db
from app.models import Category
from app.models_catalog import BeautyCenter


def test_beauty_availability_respects_public_visibility(app, client):
    with app.app_context():
        cat = Category(slug='estetica', title='Estética')
        db.session.add(cat)
        db.session.flush()

        center = BeautyCenter(name='Centro X', slug='centro-x', city='X', category_id=cat.id)
        center.show_public_booking = False
        db.session.add(center)
        db.session.commit()

        r = client.get(f"/ui/beauty/availability?beauty_slug={center.slug}")
        assert r.status_code == 403


def test_beauty_availability_ok_when_public(app, client):
    with app.app_context():
        cat = Category(slug='estetica', title='Estética')
        db.session.add(cat)
        db.session.flush()

        center = BeautyCenter(name='Centro Y', slug='centro-y', city='Y', category_id=cat.id)
        center.show_public_booking = True
        db.session.add(center)
        db.session.commit()

        # Without date/services the endpoint should still return 200 with an informational message
        r = client.get(f"/ui/beauty/availability?beauty_slug={center.slug}")
        assert r.status_code == 200
