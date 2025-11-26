from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import (
    Category,
    Complex,
    Field,
    Service,
    Timeslot,
    TimeslotStatus,
)
from app.models_catalog import BeautyCenter, Professional


def _get_or_create_category(slug: str, title: str) -> Category:
    category = Category.query.filter_by(slug=slug).first()
    if category:
        return category
    category = Category(slug=slug, title=title, description=title)
    db.session.add(category)
    db.session.flush()
    return category


def _get_or_create_service(
    slug: str,
    name: str,
    category: Category,
    duration_min: int,
    price: int,
) -> Service:
    service = Service.query.filter_by(slug=slug, category_id=category.id).first()
    if service:
        return service
    service = Service(
        name=name,
        slug=slug,
        category_id=category.id,
        duration_min=duration_min,
        base_price=price,
        currency="ARS",
    )
    db.session.add(service)
    db.session.flush()
    return service


def _get_or_create_complex(slug: str, name: str, city: str, category: Category) -> Complex:
    complex_obj = Complex.query.filter_by(slug=slug).first()
    if complex_obj:
        return complex_obj
    complex_obj = Complex(
        name=name,
        slug=slug,
        city=city,
        address=f"Direccion demo {city}",
        contact_email=f"contacto@{slug}.demo",
        contact_phone="+54 11 5555-0000",
        show_public_booking=True,
    )
    db.session.add(complex_obj)
    db.session.flush()
    complex_obj.categories.append(category)
    return complex_obj


def _get_or_create_field(complex_obj: Complex, name: str, sport: str) -> Field:
    field = Field.query.filter_by(complex_id=complex_obj.id, name=name).first()
    if field:
        return field
    field = Field(
        name=name,
        complex_id=complex_obj.id,
        sport=sport,
        surface="Cesped sintetico",
        show_public_booking=True,
    )
    db.session.add(field)
    db.session.flush()
    return field


def _get_or_create_beauty_center(
    slug: str,
    name: str,
    city: str,
    category: Category,
    service: Service,
) -> BeautyCenter:
    center = BeautyCenter.query.filter_by(slug=slug).first()
    if center:
        return center
    center = BeautyCenter(
        name=name,
        slug=slug,
        city=city,
        address=f"Direccion demo {city}",
        phone="+54 11 4444-0000",
        category_id=category.id,
        show_public_booking=True,
        booking_mode="flexible",
    )
    db.session.add(center)
    db.session.flush()
    center.linked_services.append(service)
    return center


def _get_or_create_professional(
    slug: str,
    name: str,
    city: str,
    category: Category,
    service: Service,
) -> Professional:
    prof = Professional.query.filter_by(slug=slug).first()
    if prof:
        return prof
    prof = Professional(
        name=name,
        slug=slug,
        city=city,
        specialties="Demo especialidad",
        category_id=category.id,
        show_public_booking=True,
        slot_duration_min=30,
        booking_mode="classic",
    )
    db.session.add(prof)
    db.session.flush()
    prof.linked_services.append(service)
    return prof


def _ensure_timeslot(
    start: datetime,
    end: datetime,
    price: int,
    *,
    field_id: int | None = None,
    beauty_center_id: int | None = None,
    professional_id: int | None = None,
    service_id: int | None = None,
) -> None:
    query = Timeslot.query.filter(
        Timeslot.start == start,
        Timeslot.end == end,
        Timeslot.field_id == field_id,
        Timeslot.beauty_center_id == beauty_center_id,
        Timeslot.professional_id == professional_id,
        Timeslot.service_id == service_id,
    )
    exists = query.first()
    if exists:
        return
    ts = Timeslot(
        start=start,
        end=end,
        price=price,
        currency="ARS",
        status=TimeslotStatus.AVAILABLE,
        field_id=field_id,
        beauty_center_id=beauty_center_id,
        professional_id=professional_id,
        service_id=service_id,
    )
    db.session.add(ts)


def seed_demo() -> None:
    app = create_app()
    with app.app_context():
        deportes = _get_or_create_category("deportes", "Deportes")
        estetica = _get_or_create_category("estetica", "Estetica")
        profesionales = _get_or_create_category("profesionales", "Profesionales")

        fut_service = _get_or_create_service(
            slug="turno-cancha", name="Reserva de cancha", category=deportes, duration_min=60, price=7000
        )
        hair_service = _get_or_create_service(
            slug="corte-demo", name="Corte basico", category=estetica, duration_min=30, price=3500
        )
        physio_service = _get_or_create_service(
            slug="kine-demo", name="Sesion kinesiologia", category=profesionales, duration_min=45, price=5000
        )

        complex_obj = _get_or_create_complex("demo-club", "Demo Club", "Buenos Aires", deportes)
        field = _get_or_create_field(complex_obj, "Cancha Principal", "Futbol 5")

        center = _get_or_create_beauty_center("demo-centro", "Centro Demo", "Cordoba", estetica, hair_service)
        prof = _get_or_create_professional(
            "demo-profesional", "Dra. Demo", "Rosario", profesionales, physio_service
        )

        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for day_offset in range(0, 3):
            day = base + timedelta(days=day_offset)
            # Cancha: 19 y 21 hs
            for hour in (19, 21):
                start = day.replace(hour=hour)
                end = start + timedelta(hours=1)
                _ensure_timeslot(start, end, price=8000, field_id=field.id, service_id=fut_service.id)
            # Centro de estetica: 10:00 y 11:00
            for hour in (10, 11):
                start = day.replace(hour=hour)
                end = start + timedelta(minutes=hair_service.duration_min)
                _ensure_timeslot(
                    start,
                    end,
                    price=hair_service.base_price or 3500,
                    beauty_center_id=center.id,
                    service_id=hair_service.id,
                )
            # Profesional: 15:00 y 16:00
            for hour in (15, 16):
                start = day.replace(hour=hour)
                end = start + timedelta(minutes=physio_service.duration_min or 45)
                _ensure_timeslot(
                    start,
                    end,
                    price=physio_service.base_price or 5000,
                    professional_id=prof.id,
                    service_id=physio_service.id,
                )

        db.session.commit()
        print("Demo seed ready.")


if __name__ == "__main__":
    seed_demo()
