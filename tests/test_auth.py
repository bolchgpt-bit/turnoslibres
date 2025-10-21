import pytest


def test_register_valid_user(client):
    """Registro válido redirige al login."""
    response = client.post('/admin/register', data={
        'email': 'newuser@test.com',
        'password': 'testpass123',
        'password2': 'testpass123'
    })
    assert response.status_code == 302


def test_register_duplicate_email(client, admin_user):
    """Registro con email duplicado no valida y no redirige."""
    response = client.post('/admin/register', data={
        'email': 'admin@test.com',
        'password': 'testpass123',
        'password2': 'testpass123'
    })
    # Re-renderiza el formulario (200) en vez de redirigir
    assert response.status_code == 200


def test_login_valid_credentials(client, admin_user):
    """Login válido redirige al panel."""
    response = client.post('/admin/login', data={
        'email': 'admin@test.com',
        'password': 'testpass123'
    })
    assert response.status_code == 302


def test_login_invalid_credentials(client, admin_user):
    """Login inválido re-renderiza la página de login (200)."""
    response = client.post('/admin/login', data={
        'email': 'admin@test.com',
        'password': 'wrongpassword'
    })
    assert response.status_code == 200


def test_logout(client, admin_user):
    """Logout se realiza por POST y redirige."""
    client.post('/admin/login', data={'email': 'admin@test.com', 'password': 'testpass123'})
    response = client.post('/admin/logout')
    assert response.status_code == 302


def test_admin_panel_requires_login(client):
    """El panel requiere autenticación y redirige al login."""
    response = client.get('/admin/panel')
    assert response.status_code == 302


def test_super_admin_panel_requires_super_admin(client, admin_user):
    """Acceso a /admin/super requiere superadmin → 403."""
    client.post('/admin/login', data={'email': 'admin@test.com', 'password': 'testpass123'})
    response = client.get('/admin/super')
    assert response.status_code == 403
