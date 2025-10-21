from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from app.api import bp
from app.models import Timeslot, TimeslotStatus, AppUser, Complex, Category, Service, Field, UserComplex, Subscription, SubscriptionStatus
from app.utils import user_can_manage_complex, validate_email, clean_text
from app.services.notification_service import NotificationService
from app.security import (
    validate_email as security_validate_email, 
    validate_phone, 
    sanitize_input, 
    honeypot_check, 
    validate_subscription_criteria,
    log_security_event
)
from app import db, limiter
import uuid
import json
from urllib.parse import quote
from app.models_catalog import professional_services, beauty_center_services, Professional, BeautyCenter

@bp.get('/health')
def health():
    """Endpoint de salud del API."""
    return jsonify({"status": "ok"}), 200

@bp.route('/hold', methods=['POST'])
@limiter.limit("10 per minute")
def hold_timeslot():
    """Place a timeslot on HOLDING and return a WhatsApp contact link.

    - Transitions AVAILABLE -> HOLDING atomically.
    - Builds a WhatsApp message with timeslot details and picks an admin phone:
      * Deportes: uses Complex.contact_phone
      * Profesionales/Estética: attempts Professional.phone or BeautyCenter.phone linked to the Service
    """
    timeslot_id = request.form.get('timeslot_id', type=int)
    if not timeslot_id:
        return jsonify({'success': False, 'message': 'ID de turno requerido.'}), 400

    ts = Timeslot.query.get_or_404(timeslot_id)
    if ts.status != TimeslotStatus.AVAILABLE:
        return jsonify({'success': False, 'message': 'El turno no está disponible.'}), 400

    # Build message text
    def _fmt_location() -> str:
        if ts.field:
            parts = [ts.field.complex.name or '', ts.field.name or '']
            if ts.field.sport:
                parts.append(ts.field.sport)
            return ' - '.join([p for p in parts if p])
        if ts.service:
            return ts.service.name or ''
        return ''

    def _fmt_price() -> str:
        return f"${ts.price} {ts.currency}" if ts.price else "-"

    # Deep link to admin panel for this timeslot
    base = current_app.config.get('APP_BASE_URL', '').rstrip('/')
    admin_url = f"{base}/admin/panel?focus_id={ts.id}#timeslot-{ts.id}" if base else None

    # Human-readable message (encode after composing)
    msg_text = (
        "Solicitud de reserva\n"
        f"Fecha/Hora: {ts.start.strftime('%d/%m/%Y %H:%M')}\n"
        f"Lugar/Servicio: {_fmt_location()}\n"
        f"Precio: {_fmt_price()}\n"
        f"ID: {ts.id}"
    )
    if admin_url:
        msg_text += f"\nGestionar: {admin_url}"

    # Pick phone number
    phone = None
    if ts.field and ts.field.complex and ts.field.complex.contact_phone:
        phone = ts.field.complex.contact_phone
    elif ts.service:
        # Try professional first
        prof = (
            db.session.query(Professional)
            .join(professional_services, professional_services.c.professional_id == Professional.id)
            .filter(professional_services.c.service_id == ts.service_id)
            .order_by(Professional.id)
            .first()
        )
        if prof and getattr(prof, 'phone', None):
            phone = prof.phone
        else:
            bc = (
                db.session.query(BeautyCenter)
                .join(beauty_center_services, beauty_center_services.c.beauty_center_id == BeautyCenter.id)
                .filter(beauty_center_services.c.service_id == ts.service_id)
                .order_by(BeautyCenter.id)
                .first()
            )
            if bc and getattr(bc, 'phone', None):
                phone = bc.phone

    # Clean phone to digits and plus
    def _clean_phone(p):
        if not p:
            return ''
        return ''.join(ch for ch in str(p) if ch.isdigit() or ch == '+')

    phone_clean = _clean_phone(phone)
    wa_url = f"https://wa.me/{phone_clean}?text={quote(msg_text)}" if phone_clean else None

    # Transition to HOLDING
    ts.status = TimeslotStatus.HOLDING
    db.session.commit()

    return jsonify({'success': True, 'message': 'Turno en reservando.', 'whatsapp_url': wa_url, 'admin_url': admin_url})

@bp.route('/lead', methods=['POST'])
@limiter.limit("3 per minute")
def lead():
    """Handle lead generation form submission"""
    # Honeypot check
    if request.form.get('website_url'):
        return jsonify({'success': False, 'message': 'Spam detectado.'}), 400
    
    # Get and validate form data
    business_name = clean_text(request.form.get('business_name', ''), 200)
    category = request.form.get('category', '')
    city = clean_text(request.form.get('city', ''), 100)
    contact_email = request.form.get('contact_email', '').strip().lower()
    whatsapp = clean_text(request.form.get('whatsapp', ''), 50)
    website = clean_text(request.form.get('website', ''), 200)
    services_count = request.form.get('services_count', '')
    schedule = clean_text(request.form.get('schedule', ''), 100)
    comments = clean_text(request.form.get('comments', ''), 500)
    
    # Validate required fields
    if not all([business_name, category, city, contact_email, services_count]):
        return jsonify({
            'success': False, 
            'message': 'Por favor completa todos los campos obligatorios.'
        }), 400
    
    if not validate_email(contact_email):
        return jsonify({
            'success': False, 
            'message': 'Email no vÃ¡lido.'
        }), 400
    
    try:
        services_count = int(services_count)
        if services_count < 1 or services_count > 100:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({
            'success': False, 
            'message': 'Cantidad de servicios debe ser un nÃºmero entre 1 y 100.'
        }), 400
    
    # Validate category
    category_obj = Category.query.filter_by(slug=category, is_active=True).first()
    if not category_obj:
        return jsonify({
            'success': False, 
            'message': 'CategorÃ­a no vÃ¡lida.'
        }), 400
    
    # Here you would typically save to a leads table or send an email
    # For now, we'll just log it and return success
    current_app.logger.info(f"New lead: {business_name} ({contact_email}) - {category} in {city}")
    
    return jsonify({
        'success': True, 
        'message': 'Â¡Solicitud enviada correctamente! Nos pondremos en contacto contigo pronto.'
    })

@bp.route('/admin/turnos/<int:timeslot_id>/confirm', methods=['POST'])
@login_required
def confirm_turno(timeslot_id):
    """Confirm a turno (holding -> reserved)"""
    timeslot = Timeslot.query.get_or_404(timeslot_id)
    
    # Check permissions
    if timeslot.field:
        complex_id = timeslot.field.complex_id
    elif timeslot.service:
        # For services, we need to find the complex through category relationships
        # This is a simplified check - in production you'd have a more direct relationship
        complex_id = None
        if not current_user.is_superadmin:
            return jsonify({'success': False, 'message': 'Sin permisos'}), 403
    else:
        return jsonify({'success': False, 'message': 'Turno invÃ¡lido'}), 400
    
    if complex_id and not user_can_manage_complex(current_user.id, complex_id):
        return jsonify({'success': False, 'message': 'Sin permisos para este complejo'}), 403
    
    # Check if turno can be confirmed
    if timeslot.status != TimeslotStatus.HOLDING:
        return jsonify({
            'success': False, 
            'message': 'Solo se pueden confirmar turnos en estado "Reservando"'
        }), 400
    
    # Confirm the turno
    timeslot.status = TimeslotStatus.RESERVED
    timeslot.reservation_code = str(uuid.uuid4())[:8].upper()
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f'Turno confirmado. CÃ³digo: {timeslot.reservation_code}'
    })

@bp.route('/admin/turnos/<int:timeslot_id>/release', methods=['POST'])
@login_required
def release_turno(timeslot_id):
    """Release a turno (any status -> available)"""
    timeslot = Timeslot.query.get_or_404(timeslot_id)
    
    # Check permissions
    if timeslot.field:
        complex_id = timeslot.field.complex_id
    elif timeslot.service:
        complex_id = None
        if not current_user.is_superadmin:
            return jsonify({'success': False, 'message': 'Sin permisos'}), 403
    else:
        return jsonify({'success': False, 'message': 'Turno invÃ¡lido'}), 400
    
    if complex_id and not user_can_manage_complex(current_user.id, complex_id):
        return jsonify({'success': False, 'message': 'Sin permisos para este complejo'}), 403
    
    # Release the turno
    old_status = timeslot.status
    timeslot.status = TimeslotStatus.AVAILABLE
    timeslot.reservation_code = None
    db.session.commit()
    
    if old_status != TimeslotStatus.AVAILABLE:
        try:
            NotificationService.notify_timeslot_available(timeslot_id)
        except Exception as e:
            current_app.logger.error(f"Error triggering notifications: {str(e)}")
    
    return jsonify({
        'success': True, 
        'message': 'Turno liberado correctamente'
    })

# Super Admin API Routes
@bp.route('/admin/categories', methods=['POST'])
@login_required
def create_category():
    """Create new category"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    slug = clean_text(data.get('slug', ''), 50)
    title = clean_text(data.get('title', ''), 100)
    description = clean_text(data.get('description', ''), 500)
    
    if not slug or not title:
        return jsonify({'success': False, 'message': 'Slug y tÃ­tulo son requeridos'}), 400
    
    # Check if slug already exists
    if Category.query.filter_by(slug=slug).first():
        return jsonify({'success': False, 'message': 'El slug ya existe'}), 400
    
    category = Category(slug=slug, title=title, description=description)
    db.session.add(category)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'CategorÃ­a creada correctamente'})

@bp.route('/admin/categories/<int:category_id>', methods=['DELETE'])
@login_required
def delete_category(category_id):
    """Delete category"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    category = Category.query.get_or_404(category_id)
    
    # Check if category has services
    if category.services:
        return jsonify({
            'success': False, 
            'message': 'No se puede eliminar una categorÃ­a con servicios asociados'
        }), 400
    
    db.session.delete(category)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'CategorÃ­a eliminada correctamente'})

@bp.route('/admin/complex-category/link', methods=['POST'])
@login_required
def link_complex_category():
    """Link complex to category"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    complex_id = data.get('complex_id')
    category_id = data.get('category_id')
    
    if not complex_id or not category_id:
        return jsonify({'success': False, 'message': 'IDs requeridos'}), 400
    
    complex_obj = Complex.query.get_or_404(complex_id)
    category = Category.query.get_or_404(category_id)
    
    if category not in complex_obj.categories:
        complex_obj.categories.append(category)
        db.session.commit()
        return jsonify({'success': True, 'message': 'VinculaciÃ³n creada correctamente'})
    else:
        return jsonify({'success': False, 'message': 'Ya estÃ¡n vinculados'}), 400

@bp.route('/admin/complex-category/unlink', methods=['POST'])
@login_required
def unlink_complex_category():
    """Unlink complex from category"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    complex_id = data.get('complex_id')
    category_id = data.get('category_id')
    
    if not complex_id or not category_id:
        return jsonify({'success': False, 'message': 'IDs requeridos'}), 400
    
    complex_obj = Complex.query.get_or_404(complex_id)
    category = Category.query.get_or_404(category_id)
    
    if category in complex_obj.categories:
        complex_obj.categories.remove(category)
        db.session.commit()
        return jsonify({'success': True, 'message': 'VinculaciÃ³n eliminada correctamente'})
    else:
        return jsonify({'success': False, 'message': 'No estÃ¡n vinculados'}), 400

@bp.route('/subscribe', methods=['POST'])
@limiter.limit("5 per minute")
def subscribe():
    """Handle subscription to timeslot notifications"""
    # Honeypot check
    if not honeypot_check(request.form):
        log_security_event('honeypot_triggered', {'ip': request.remote_addr})
        return jsonify({'success': False, 'message': 'Solicitud invÃ¡lida.'}), 400
    
    email = sanitize_input(request.form.get('email', ''), 255).lower()
    timeslot_id = request.form.get('timeslot_id')
    criteria_json = request.form.get('criteria')
    
    # Validate email
    if not email or not security_validate_email(email):
        return jsonify({'success': False, 'message': 'Email no vÃ¡lido.'}), 400
    
    # Validate subscription type
    if timeslot_id and criteria_json:
        return jsonify({'success': False, 'message': 'Solo puedes suscribirte a un turno especÃ­fico O con criterios, no ambos.'}), 400
    
    if not timeslot_id and not criteria_json:
        return jsonify({'success': False, 'message': 'Debes especificar un turno o criterios de bÃºsqueda.'}), 400
    
    try:
        if timeslot_id:
            # Direct timeslot subscription
            try:
                timeslot_id_int = int(timeslot_id)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'Turno inválido.'}), 400

            timeslot = Timeslot.query.get_or_404(timeslot_id_int)

            # Check if already subscribed
            existing = Subscription.query.filter(
                Subscription.email == email,
                Subscription.timeslot_id == timeslot_id_int,
                Subscription.is_active.is_(True),
                Subscription.status == SubscriptionStatus.ACTIVE,
            ).first()

            if existing:
                return jsonify({'success': False, 'message': 'Ya estás suscrito a este turno.'}), 400

            subscription = Subscription(email=email, timeslot_id=timeslot_id_int)

        else:
            # Criteria-based subscription
            try:
                criteria = json.loads(criteria_json)
            except json.JSONDecodeError:
                return jsonify({'success': False, 'message': 'Criterios invÃ¡lidos.'}), 400
            
            if not validate_subscription_criteria(criteria):
                return jsonify({'success': False, 'message': 'Criterios de bÃºsqueda invÃ¡lidos.'}), 400
            
            subscription = Subscription(email=email, criteria=criteria)
        
        db.session.add(subscription)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'SuscripciÃ³n creada correctamente. Te notificaremos cuando haya turnos disponibles.',
            'subscription_id': subscription.id
        })
        
    except Exception as e:
        current_app.logger.error(f"Subscription error: {str(e)}")
        return jsonify({'success': False, 'message': 'Error interno del servidor.'}), 500

@bp.route('/unsubscribe', methods=['POST'])
def unsubscribe():
    """Handle unsubscription from notifications"""
    subscription_id = request.form.get('subscription_id')
    
    if not subscription_id:
        return jsonify({'success': False, 'message': 'ID de suscripciÃ³n requerido.'}), 400
    
    try:
        subscription = Subscription.query.get_or_404(int(subscription_id))
        subscription.is_active = False
        subscription.status = SubscriptionStatus.UNSUBSCRIBED
        db.session.commit()

        return jsonify({'success': True, 'message': 'Te has desuscrito correctamente.'})
        
    except Exception as e:
        current_app.logger.error(f"Unsubscribe error: {str(e)}")
        return jsonify({'success': False, 'message': 'Error interno del servidor.'}), 500

@bp.route('/leads', methods=['POST'])
@limiter.limit("3 per minute")
def leads():
    """Handle lead generation form submission"""
    # Honeypot check
    if not honeypot_check(request.form):
        log_security_event('honeypot_triggered', {'ip': request.remote_addr, 'form': 'leads'})
        return jsonify({'success': False, 'message': 'Solicitud invÃ¡lida.'}), 400
    
    # Get and validate form data
    name = sanitize_input(request.form.get('name', ''), 200)
    email = sanitize_input(request.form.get('email', ''), 255).lower()
    phone = sanitize_input(request.form.get('phone', ''), 50)
    business_type = request.form.get('business_type', '')
    message = sanitize_input(request.form.get('message', ''), 1000)
    
    # Validate required fields
    if not all([name, email, business_type]):
        return jsonify({
            'success': False, 
            'message': 'Por favor completa todos los campos obligatorios.'
        }), 400
    
    if not security_validate_email(email):
        return jsonify({'success': False, 'message': 'Email no vÃ¡lido.'}), 400
    
    if phone and not validate_phone(phone):
        return jsonify({'success': False, 'message': 'TelÃ©fono no vÃ¡lido.'}), 400
    
    # Validate business type
    allowed_types = ['deportes', 'estetica', 'profesionales']
    if business_type not in allowed_types:
        return jsonify({'success': False, 'message': 'Tipo de negocio no vÃ¡lido.'}), 400
    
    # Log the lead (in production, you'd save to database or send email)
    current_app.logger.info(f"New lead: {name} ({email}) - {business_type}")
    
    return jsonify({
        'success': True, 
        'message': 'Â¡Solicitud enviada correctamente! Nos pondremos en contacto contigo pronto.'
    })
