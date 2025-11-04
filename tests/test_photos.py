def test_complex_photos_requires_login(client, app):
    from app import db
    from app.models import Complex
    with app.app_context():
        c = Complex(name='La verde', slug='laverde', city='CABA')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    # Not logged in -> should redirect to login
    resp = client.get(f'/admin/complex_photos?complex_id={cid}', follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_complex_photos_superadmin_ok(client, app, super_admin_user):
    from app import db
    from app.models import Complex
    # Create complex
    with app.app_context():
        c = Complex(name='La verde', slug='laverde', city='CABA')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    # Login as super admin
    client.post('/admin/login', data={'email': 'superadmin@test.com', 'password': 'testpass123'})

    resp = client.get(f'/admin/complex_photos?complex_id={cid}')
    assert resp.status_code == 200
    assert b'Fotos de' in resp.data

