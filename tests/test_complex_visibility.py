from app import db
from app.models import Complex, Category


def test_turnos_table_respects_complex_public_visibility(app, client):
    with app.app_context():
        # Ensure category exists for validation purposes
        cat = Category(slug='deportes', title='Deportes')
        db.session.add(cat)
        db.session.flush()

        cpx = Complex(name='Complejo X', slug='complejo-x', city='X')
        cpx.show_public_booking = False
        db.session.add(cpx)
        db.session.commit()

        r = client.get('/ui/turnos_table?category=deportes&complex_slug=complejo-x')
        assert r.status_code == 403


def test_turnos_table_ok_when_public_complex(app, client):
    with app.app_context():
        cat = Category(slug='deportes', title='Deportes')
        db.session.add(cat)
        db.session.flush()

        cpx = Complex(name='Complejo Y', slug='complejo-y', city='Y')
        cpx.show_public_booking = True
        db.session.add(cpx)
        db.session.commit()

        r = client.get('/ui/turnos_table?category=deportes&complex_slug=complejo-y')
        assert r.status_code == 200

