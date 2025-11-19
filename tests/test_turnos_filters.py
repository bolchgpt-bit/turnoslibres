import pytest
from datetime import datetime, timedelta, timezone
from app import db
from app.models import Category, Complex, Field, Timeslot, TimeslotStatus


@pytest.fixture
def complex_with_turnos(app):
    with app.app_context():
        cat = Category(slug='deportes', title='Deportes')
        db.session.add(cat)
        db.session.flush()

        cpx = Complex(name='Complejo Default', slug='complejo-default', city='X', show_public_booking=True)
        cpx.categories.append(cat)
        db.session.add(cpx)
        db.session.flush()

        field = Field(
            complex_id=cpx.id,
            name='Cancha 1',
            sport='futbol',
            is_active=True,
            show_public_booking=True
        )
        db.session.add(field)
        db.session.flush()

        now = datetime.now(timezone.utc)
        available = Timeslot(
            field_id=field.id,
            start=now + timedelta(hours=2),
            end=now + timedelta(hours=3),
            status=TimeslotStatus.AVAILABLE
        )
        reserved = Timeslot(
            field_id=field.id,
            start=now + timedelta(hours=4),
            end=now + timedelta(hours=5),
            status=TimeslotStatus.RESERVED
        )
        db.session.add_all([available, reserved])
        db.session.commit()

        return {
            'complex_slug': cpx.slug,
            'available_id': available.id,
            'reserved_id': reserved.id
        }


def test_turnos_table_defaults_to_available(client, complex_with_turnos):
    slug = complex_with_turnos['complex_slug']
    response = client.get(f"/ui/turnos_table?category=deportes&complex_slug={slug}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"status-{complex_with_turnos['available_id']}" in html
    assert f"status-{complex_with_turnos['reserved_id']}" not in html


def test_turnos_table_allows_all_statuses(client, complex_with_turnos):
    slug = complex_with_turnos['complex_slug']
    response = client.get(f"/ui/turnos_table?category=deportes&complex_slug={slug}&status=all")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"status-{complex_with_turnos['available_id']}" in html
    assert f"status-{complex_with_turnos['reserved_id']}" in html
