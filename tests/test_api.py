import pytest
import json
from app.models import Subscription
from app import db

def test_subscribe_to_timeslot(client, sample_data):
    """Test subscribing to a specific timeslot"""
    timeslot = sample_data['timeslot']
    
    response = client.post('/api/subscribe', data={
        'email': 'user@test.com',
        'timeslot_id': timeslot.id
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'subscription_id' in data

def test_subscribe_with_criteria(client, sample_data):
    """Test subscribing with criteria"""
    category = sample_data['category']
    
    response = client.post('/api/subscribe', data={
        'email': 'user@test.com',
        'criteria': json.dumps({
            'category': category.name,
            'max_price': 100.0
        })
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True

def test_subscribe_invalid_email(client, sample_data):
    """Test subscription with invalid email"""
    timeslot = sample_data['timeslot']
    
    response = client.post('/api/subscribe', data={
        'email': 'invalid-email',
        'timeslot_id': timeslot.id
    })
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False

def test_honeypot_protection(client, sample_data):
    """Test honeypot spam protection"""
    timeslot = sample_data['timeslot']
    
    response = client.post('/api/subscribe', data={
        'email': 'user@test.com',
        'timeslot_id': timeslot.id,
        'website': 'spam-content'  # Honeypot field
    })
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False

def test_unsubscribe(client, sample_data):
    """Test unsubscribing from notifications"""
    # First create a subscription
    subscription = Subscription(
        email='user@test.com',
        timeslot_id=sample_data['timeslot'].id
    )
    db.session.add(subscription)
    db.session.commit()
    
    response = client.post('/api/unsubscribe', data={
        'subscription_id': subscription.id
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True

def test_lead_generation(client):
    """Test lead generation form"""
    response = client.post('/api/leads', data={
        'name': 'Test Business',
        'email': 'business@test.com',
        'phone': '+1234567890',
        'business_type': 'deportes',
        'message': 'Interested in publishing turnos'
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True


def test_hold_generates_clean_whatsapp_link(client, sample_data):
    """Hold endpoint should return a wa.me link with digits only."""
    timeslot = sample_data['timeslot']

    response = client.post('/api/hold', data={'timeslot_id': timeslot.id})

    assert response.status_code == 200
    payload = json.loads(response.data)
    assert payload['success'] is True
    assert payload['whatsapp_url'].startswith('https://wa.me/5491112345678')
    assert 'Solicitud%20de%20reserva' in payload['whatsapp_url']
