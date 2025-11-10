from datetime import datetime, timedelta, timezone

from app import db
from app.models import Category, Service, Timeslot
from app.models_catalog import BeautyCenter, beauty_center_services


def _create_estetica_category():
    cat = Category(slug='estetica', title='Estética')
    db.session.add(cat)
    db.session.flush()
    return cat


def _link_center_service(center: BeautyCenter, service: Service) -> None:
    db.session.execute(
        beauty_center_services.insert().values(beauty_center_id=center.id, service_id=service.id)
    )
    db.session.flush()


def test_quick_form_filters_centers_for_fixed_mode(app, client, super_admin_user):
    with app.app_context():
        # Setup: category, two services, one center fixed to service A
        cat = _create_estetica_category()
        srv_a = Service(category_id=cat.id, name='Corte', slug='corte', duration_min=30, is_active=True)
        srv_b = Service(category_id=cat.id, name='Tintura', slug='tintura', duration_min=60, is_active=True)
        center = BeautyCenter(name='Centro Solo Cortes', slug='solo-cortes', city='CABA', category_id=cat.id)
        center.show_public_booking = True
        db.session.add_all([srv_a, srv_b, center])
        db.session.flush()
        _link_center_service(center, srv_a)
        _link_center_service(center, srv_b)
        # Fijar modo fijo al servicio A
        center.booking_mode = 'fixed'  # type: ignore[attr-defined]
        center.fixed_service_id = srv_a.id  # type: ignore[attr-defined]
        db.session.commit()

        # Login superadmin
        client.post('/admin/login', data={'email': 'superadmin@test.com', 'password': 'testpass123'})

        # Pedir quick form para servicio B: el centro no debe aparecer
        r = client.get(f"/admin/timeslots/quick_form_beauty?service_id={srv_b.id}")
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        assert 'Centro Solo Cortes' not in html

        # Para servicio A sí debe aparecer
        r2 = client.get(f"/admin/timeslots/quick_form_beauty?service_id={srv_a.id}")
        assert r2.status_code == 200
        html2 = r2.data.decode('utf-8')
        assert 'Centro Solo Cortes' in html2


def test_create_timeslot_enforces_fixed_mode(app, client, super_admin_user):
    with app.app_context():
        cat = _create_estetica_category()
        srv_a = Service(category_id=cat.id, name='Corte', slug='corte', duration_min=30, is_active=True)
        srv_b = Service(category_id=cat.id, name='Tintura', slug='tintura', duration_min=60, is_active=True)
        center = BeautyCenter(name='Centro Solo Cortes', slug='solo-cortes-2', city='CABA', category_id=cat.id)
        center.show_public_booking = True
        db.session.add_all([srv_a, srv_b, center])
        db.session.flush()
        _link_center_service(center, srv_a)
        _link_center_service(center, srv_b)
        center.booking_mode = 'fixed'  # type: ignore[attr-defined]
        center.fixed_service_id = srv_a.id  # type: ignore[attr-defined]
        db.session.commit()

        client.post('/admin/login', data={'email': 'superadmin@test.com', 'password': 'testpass123'})

        # Intentar crear con servicio no permitido (B)
        start = datetime.now(timezone.utc) + timedelta(hours=2)
        resp = client.post('/admin/timeslots/create_for_service_quick_beauty', data={
            'service_id': srv_b.id,
            'center_id': center.id,
            'start': start.strftime('%Y-%m-%dT%H:%M'),
            'price': '1000',
        })
        assert resp.status_code == 200
        assert db.session.query(Timeslot).count() == 0

        # Crear con servicio permitido (A)
        resp_ok = client.post('/admin/timeslots/create_for_service_quick_beauty', data={
            'service_id': srv_a.id,
            'center_id': center.id,
            'start': start.strftime('%Y-%m-%dT%H:%M'),
            'price': '1200',
        })
        assert resp_ok.status_code == 200
        ts = db.session.query(Timeslot).first()
        assert ts is not None
        assert ts.service_id == srv_a.id
        assert ts.beauty_center_id == center.id
        assert int((ts.end - ts.start).total_seconds() // 60) == srv_a.duration_min

