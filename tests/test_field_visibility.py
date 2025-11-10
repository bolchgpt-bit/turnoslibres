from datetime import datetime, timedelta, timezone

from app import db
from app.models import Complex, Field, Timeslot, TimeslotStatus, Category


def test_hidden_field_timeslots_are_excluded_in_day_view(app, client):
    with app.app_context():
        cat = Category(slug='deportes', title='Deportes')
        db.session.add(cat)
        db.session.flush()

        cpx = Complex(name='Complejo Z', slug='complejo-z', city='Z', show_public_booking=True)
        db.session.add(cpx)
        db.session.flush()

        fld_hidden = Field(complex_id=cpx.id, name='Cancha Oculta', sport='futbol', is_active=True, show_public_booking=False)
        db.session.add(fld_hidden)
        db.session.flush()

        # Create a future timeslot for the hidden field
        now = datetime.now(timezone.utc)
        ts = Timeslot(field_id=fld_hidden.id, start=now + timedelta(hours=2), end=now + timedelta(hours=3), status=TimeslotStatus.AVAILABLE)
        db.session.add(ts)
        db.session.commit()

        r = client.get('/ui/turnos_table?category=deportes&complex_slug=complejo-z')
        assert r.status_code == 200
        # Should show 0 turnos encontrados because the only slot belongs to a hidden field
        assert b'0 turnos encontrados' in r.data


def test_visible_field_timeslots_appear_in_day_view(app, client):
    with app.app_context():
        cat = Category(slug='deportes', title='Deportes')
        db.session.add(cat)
        db.session.flush()

        cpx = Complex(name='Complejo W', slug='complejo-w', city='W', show_public_booking=True)
        db.session.add(cpx)
        db.session.flush()

        fld = Field(complex_id=cpx.id, name='Cancha Pública', sport='tenis', is_active=True, show_public_booking=True)
        db.session.add(fld)
        db.session.flush()

        now = datetime.now(timezone.utc)
        ts = Timeslot(field_id=fld.id, start=now + timedelta(hours=2), end=now + timedelta(hours=3), status=TimeslotStatus.AVAILABLE)
        db.session.add(ts)
        db.session.commit()

        r = client.get('/ui/turnos_table?category=deportes&complex_slug=complejo-w')
        assert r.status_code == 200
        assert b'turnos encontrados' in r.data and b'0 turnos encontrados' not in r.data

