from datetime import date, time

from app import db
from app.models import Complex, Field, Timeslot
from app.services.timeslot_generation import generate_timeslots_for_field


def test_generate_timeslots_for_field_basic(app):
    with app.app_context():
        complex_ = Complex(name="Test Complex", slug="test-complex", city="X")
        db.session.add(complex_)
        db.session.flush()

        field = Field(complex_id=complex_.id, name="Cancha 1", sport="futbol", team_size=5)
        db.session.add(field)
        db.session.commit()

        created, skipped = generate_timeslots_for_field(
            field=field,
            start_date=date.today(),
            end_date=date.today(),
            start_time=time(9, 0),
            end_time=time(12, 0),
            duration_min=60,
            interval_min=60,
            weekdays=[date.today().weekday()],
            price=1000.0,
            currency="ARS",
        )

        assert created == 3  # 09-10, 10-11, 11-12
        assert skipped == 0
        assert db.session.query(Timeslot).count() == 3

