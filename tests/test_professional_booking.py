from datetime import date, time, datetime, timedelta, timezone

from app import db
from app.models import Timeslot, TimeslotStatus, Category, Service, Subscription
from app.models_catalog import Professional, professional_services, DailyAvailability
from app.services.timeslot_generation import generate_timeslots_for_professional


def create_category(slug: str = 'profesionales'):
    cat = Category(slug=slug, title=slug.title())
    db.session.add(cat)
    db.session.flush()
    return cat


def test_generate_timeslots_for_professional_basic(app):
    with app.app_context():
        cat = create_category('profesionales')
        prof = Professional(name='Dra. Test', slug='dra-test', city='X', category_id=cat.id)
        db.session.add(prof)
        svc = Service(category_id=cat.id, name='Sesión 60', slug='sesion-60', duration_min=60, is_active=True)
        db.session.add(svc)
        db.session.commit()

        created, skipped = generate_timeslots_for_professional(
            professional=prof,
            service_id=svc.id,
            start_date=date.today(),
            end_date=date.today(),
            start_time=time(9, 0),
            end_time=time(12, 0),
            duration_min=60,
            interval_min=60,
            weekdays=[date.today().weekday()],
            price=1500.0,
            currency='ARS',
        )

        assert created == 3
        assert skipped == 0
        slots = Timeslot.query.order_by(Timeslot.start).all()
        assert len(slots) == 3
        assert all(s.professional_id == prof.id and s.service_id == svc.id for s in slots)


def test_prof_day_calendar_and_booking_flow(app, client):
    with app.app_context():
        cat = create_category('profesionales')
        prof = Professional(name='Plomero X', slug='plomero-x', city='Y', category_id=cat.id, booking_mode='per_day', daily_quota=1)
        db.session.add(prof)
        db.session.commit()

        # Calendar should render with 200
        r = client.get(f'/ui/prof/day_calendar?slug={prof.slug}')
        assert r.status_code == 200
        assert b'Cupos' in r.data

        # Book for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        r2 = client.post('/ui/prof/book_day', data={
            'slug': prof.slug,
            'date': tomorrow.isoformat(),
            'email': 'user@example.com',
        })
        assert r2.status_code == 200
        assert b'Reserva tomada' in r2.data

        # Capacity should increase reserved_count
        rec = DailyAvailability.query.filter_by(professional_id=prof.id, date=tomorrow).first()
        assert rec is not None
        assert int(rec.reserved_count) == 1

        # Subscription created
        sub = Subscription.query.first()
        assert sub is not None
        assert sub.email == 'user@example.com'


def test_prof_availability_classic_smoke(app, client):
    with app.app_context():
        cat = create_category('profesionales')
        prof = Professional(name='Psico Y', slug='psico-y', city='Z', category_id=cat.id, booking_mode='classic')
        db.session.add(prof)
        svc = Service(category_id=cat.id, name='Sesión', slug='sesion', duration_min=60, is_active=True)
        db.session.add(svc)
        db.session.commit()

        now = datetime.now(timezone.utc)
        # Create two future slots
        for i in range(2):
            s = Timeslot(
                professional_id=prof.id,
                service_id=svc.id,
                start=now + timedelta(hours=2 + i),
                end=now + timedelta(hours=3 + i),
                status=TimeslotStatus.AVAILABLE,
            )
            db.session.add(s)
        db.session.commit()

        r = client.get(f'/ui/prof/availability?slug={prof.slug}')
        assert r.status_code == 200
        # Should include times like dd/mm hh:mm
        assert b'Horarios' in r.data or b'No hay horarios' in r.data

