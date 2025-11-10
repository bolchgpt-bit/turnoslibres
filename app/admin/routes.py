from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.admin import bp
from app.admin.forms import LoginForm, RegistrationForm, ProfessionalForm, BeautyCenterForm, SportsComplexForm
from app.models import AppUser, Complex, Category, Service, Field, Timeslot, TimeslotStatus, UserComplex, user_professionals, user_beauty_centers
from app.models_catalog import Professional, BeautyCenter, SportsComplex, professional_services, beauty_center_services
from app import db
from app.services.timeslot_generation import generate_timeslots_for_field, generate_timeslots_for_professional
from app.security import superadmin_required
from app.utils import (
    user_can_manage_complex,
    validate_date_format,
    validate_span,
    validate_category,
    validate_status,
    clean_text,
    validate_email,
)
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from markupsafe import escape
import os
import uuid
from werkzeug.utils import secure_filename
from app.models_catalog import BeautyCenter
from app.models_catalog import Professional
from app.models import user_beauty_centers, user_professionals
from app.models_catalog import Professional

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Autentica usuarios administradores y redirige al panel."""
    if current_user.is_authenticated:
        return redirect(url_for('admin.panel'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = AppUser.query.filter_by(email=form.email.data.lower()).first()
        
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('admin.panel')
            flash('Sesión iniciada correctamente.', 'success')
            return redirect(next_page)
        else:
            flash('Email o contraseña incorrectos.', 'error')
    
    return render_template('admin/login.html', form=form)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registra un nuevo usuario administrador básico."""
    if current_user.is_authenticated:
        return redirect(url_for('admin.panel'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = AppUser(email=form.email.data.lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash('Registro exitoso. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('admin.login'))
    
    return render_template('admin/register.html', form=form)

@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Cierra la sesión del usuario actual."""
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('main.index'))

@bp.route('/panel')
@login_required
def panel():
    """Muestra el panel de administración."""
    return render_template('admin/panel.html')

@bp.route('/professional_settings')
@login_required
def professional_settings():
    """HTMX partial listing professional booking settings (superadmin or profesionales)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []

    return render_template('admin/partials/_professional_settings.html', professionals=professionals)

@bp.route('/professional_settings/update', methods=['POST'])
@login_required
def professional_update_settings():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    prof_id = request.form.get('professional_id', type=int)
    mode = request.form.get('booking_mode', 'classic')
    slot_duration_min = request.form.get('slot_duration_min', type=int)
    daily_quota = request.form.get('daily_quota', type=int)
    show_public_booking = bool(request.form.get('show_public_booking'))

    prof = Professional.query.get_or_404(prof_id)
    # Scope: user must be linked unless superadmin
    if not current_user.is_superadmin:
        link = db.session.execute(
            db.select(user_professionals).where(
                user_professionals.c.user_id == current_user.id,
                user_professionals.c.professional_id == prof.id,
            )
        ).first()
        if not link:
            return jsonify({'error': 'Unauthorized'}), 403

    if mode not in ('classic', 'per_day'):
        mode = 'classic'
    prof.booking_mode = mode
    if slot_duration_min is not None:
        if slot_duration_min <= 0 or slot_duration_min > 480:
            slot_duration_min = None
        prof.slot_duration_min = slot_duration_min
    if daily_quota is not None:
        if daily_quota < 0 or daily_quota > 100:
            daily_quota = 0
        prof.daily_quota = daily_quota

    prof.show_public_booking = show_public_booking
    db.session.commit()

    # Rerender settings table
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []
    return render_template('admin/partials/_professional_settings.html', professionals=professionals, message_text='Guardado', message_category='success')

@bp.route('/pro_timeslots/bulk_form')
@login_required
def pro_timeslots_bulk_form():
    """HTMX partial to generate timeslots in bulk for professionals."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []
    return render_template('admin/partials/_pro_timeslot_bulk_form.html', professionals=professionals)

@bp.route('/pro_timeslots/bulk_create', methods=['POST'])
@login_required
def pro_timeslots_bulk_create():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    professional_id = request.form.get('professional_id', type=int)
    service_id = request.form.get('service_id', type=int)
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    duration_min = request.form.get('duration_min', type=int)
    interval_min = request.form.get('interval_min', type=int)
    weekdays = request.form.getlist('weekdays')
    price_raw = (request.form.get('price') or '').strip()
    currency = (request.form.get('currency') or 'ARS').strip()[:3]

    msg = ''
    cat = 'success'

    prof = Professional.query.get(professional_id) if professional_id else None
    srv = Service.query.get(service_id) if service_id else None

    if not prof or not srv or not srv.is_active:
        msg, cat = 'Datos inválidos', 'error'

    # Scope
    if cat == 'success' and not current_user.is_superadmin:
        link = db.session.execute(
            db.select(user_professionals).where(
                user_professionals.c.user_id == current_user.id,
                user_professionals.c.professional_id == prof.id,
            )
        ).first()
        if not link:
            return jsonify({'error': 'Unauthorized'}), 403
        if srv not in prof.linked_services:
            msg, cat = 'El servicio no está vinculado al profesional', 'error'

    # Parse dates/times
    if cat == 'success':
        try:
            from datetime import datetime as _dt, time as _time
            sd = _dt.strptime(start_date, '%Y-%m-%d').date()
            ed = _dt.strptime(end_date, '%Y-%m-%d').date()
            st = _dt.strptime(start_time, '%H:%M').time()
            et = _dt.strptime(end_time, '%H:%M').time()
        except Exception:
            msg, cat = 'Fechas/horas inválidas', 'error'

    # Duration default to service
    if cat == 'success':
        dur = int(duration_min or int(srv.duration_min or 60))
        step = int(interval_min or dur)
        if dur < 15 or dur > 360:
            msg, cat = 'Duración inválida', 'error'

    # Price
    price = None
    if cat == 'success' and price_raw:
        try:
            price = float(price_raw.replace(',', '.'))
            if price < 0:
                raise ValueError()
        except Exception:
            msg, cat = 'Precio inválido', 'error'

    # Weekdays
    if cat == 'success':
        try:
            wds = [int(w) for w in weekdays] if weekdays else [0,1,2,3,4]
        except Exception:
            wds = [0,1,2,3,4]

        created, skipped = generate_timeslots_for_professional(
            professional=prof,
            service_id=srv.id,
            start_date=sd,
            end_date=ed,
            start_time=st,
            end_time=et,
            duration_min=dur,
            interval_min=step,
            weekdays=wds,
            price=price,
            currency=currency or 'ARS',
        )
        msg = f'Turnos creados: {created}, omitidos: {skipped}'

    # Rerender form
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []
    return render_template('admin/partials/_pro_timeslot_bulk_form.html', professionals=professionals, message_text=msg, message_category=cat)

@bp.route('/super')
@login_required
@superadmin_required
def super_admin():
    """Vista exclusiva para superadministradores."""
    if not current_user.is_superadmin:
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('admin.panel'))
    
    return render_template('admin/super.html')


def _allowed_image(filename: str) -> bool:
    exts = {'.jpg', '.jpeg', '.png', '.webp'}
    name = (filename or '').lower()
    return any(name.endswith(e) for e in exts)


@bp.route('/complex_photos')
@login_required
def complex_photos():
    """HTMX partial to manage complex photos (max 10)."""
    complex_id = request.args.get('complex_id', type=int)
    if not complex_id:
        return jsonify({'error': 'complex_id requerido'}), 400
    cpx = Complex.query.get_or_404(complex_id)

    # Authorization: superadmin or linked to complex
    if not (current_user.is_superadmin or user_can_manage_complex(current_user, cpx.id)):
        return jsonify({'error': 'Unauthorized'}), 403

    photos = cpx.photos
    return render_template('admin/partials/_complex_photos.html', complex=cpx, photos=photos)


@bp.route('/complex_photos/upload', methods=['POST'])
@login_required
def complex_photos_upload():
    complex_id = request.form.get('complex_id', type=int)
    if not complex_id:
        return jsonify({'error': 'complex_id requerido'}), 400
    cpx = Complex.query.get_or_404(complex_id)

    if not (current_user.is_superadmin or user_can_manage_complex(current_user, cpx.id)):
        return jsonify({'error': 'Unauthorized'}), 403

    message_text = None
    message_category = None

    # Limit to 10
    if len(cpx.photos) >= 10:
        message_text = 'Límite de 10 fotos alcanzado'
        message_category = 'error'
    else:
        file = request.files.get('photo')
        if not file or not file.filename:
            message_text = 'Archivo requerido'
            message_category = 'error'
        elif not _allowed_image(file.filename):
            message_text = 'Formato no permitido (solo JPG, PNG, WEBP)'
            message_category = 'error'
        else:
            # Build path under static/uploads/complexes/<slug>/
            base_static = current_app.config.get('STATIC_ROOT', None)
            # Default to app/static if not configured
            if not base_static:
                base_static = os.path.join(current_app.root_path, 'static')
            rel_dir = os.path.join('uploads', 'complexes', cpx.slug)
            abs_dir = os.path.join(base_static, rel_dir)
            os.makedirs(abs_dir, exist_ok=True)

            ext = os.path.splitext(file.filename)[1].lower()
            fname = secure_filename(f"{uuid.uuid4().hex}{ext}")
            abs_path = os.path.join(abs_dir, fname)
            rel_path = os.path.join(rel_dir, fname).replace('\\', '/')

            try:
                file.save(abs_path)
                # Rank next
                next_rank = (cpx.photos[-1].rank + 1) if cpx.photos else 0
                from app.models import ComplexPhoto  # local import to avoid circular
                photo = ComplexPhoto(complex_id=cpx.id, path=rel_path, rank=next_rank)
                db.session.add(photo)
                db.session.commit()
                message_text = 'Foto subida correctamente'
                message_category = 'success'
            except Exception as e:
                current_app.logger.exception('Upload failed: %s', e)
                message_text = 'No se pudo subir la foto'
                message_category = 'error'

    return render_template('admin/partials/_complex_photos.html', complex=cpx, photos=cpx.photos,
                          message_text=message_text, message_category=message_category)


@bp.route('/complex_photos/delete', methods=['POST'])
@login_required
def complex_photos_delete():
    photo_id = request.form.get('photo_id', type=int)
    if not photo_id:
        return jsonify({'error': 'photo_id requerido'}), 400
    from app.models import ComplexPhoto
    photo = ComplexPhoto.query.get_or_404(photo_id)
    cpx = Complex.query.get_or_404(photo.complex_id)

    if not (current_user.is_superadmin or user_can_manage_complex(current_user, cpx.id)):
        return jsonify({'error': 'Unauthorized'}), 403

    # Remove file best-effort
    try:
        base_static = current_app.config.get('STATIC_ROOT', None) or os.path.join(current_app.root_path, 'static')
        abs_path = os.path.join(base_static, photo.path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except Exception as e:
        current_app.logger.warning('Could not delete photo file: %s', e)

    db.session.delete(photo)
    db.session.commit()

    return render_template('admin/partials/_complex_photos.html', complex=cpx, photos=cpx.photos,
                          message_text='Foto eliminada', message_category='success')


@bp.route('/beauty_photos')
@login_required
def beauty_photos():
    center_id = request.args.get('center_id', type=int)
    if not center_id:
        return jsonify({'error': 'center_id requerido'}), 400
    center = BeautyCenter.query.get_or_404(center_id)

    # Authorization: superadmin or user linked to center via user_beauty_centers
    allowed = False
    if current_user.is_superadmin:
        allowed = True
    else:
        link = db.session.execute(
            db.select(user_beauty_centers).where(
                user_beauty_centers.c.user_id == current_user.id,
                user_beauty_centers.c.beauty_center_id == center.id,
            )
        ).first()
        allowed = bool(link)
    if not allowed:
        return jsonify({'error': 'Unauthorized'}), 403

    return render_template('admin/partials/_beauty_photos.html', center=center, photos=center.photos)


@bp.route('/beauty_photos/upload', methods=['POST'])
@login_required
def beauty_photos_upload():
    center_id = request.form.get('center_id', type=int)
    if not center_id:
        return jsonify({'error': 'center_id requerido'}), 400
    center = BeautyCenter.query.get_or_404(center_id)

    allowed = False
    if current_user.is_superadmin:
        allowed = True
    else:
        link = db.session.execute(
            db.select(user_beauty_centers).where(
                user_beauty_centers.c.user_id == current_user.id,
                user_beauty_centers.c.beauty_center_id == center.id,
            )
        ).first()
        allowed = bool(link)
    if not allowed:
        return jsonify({'error': 'Unauthorized'}), 403

    message_text = None
    message_category = None

    if len(center.photos) >= 10:
        message_text = 'Límite de 10 fotos alcanzado'
        message_category = 'error'
    else:
        file = request.files.get('photo')
        if not file or not file.filename:
            message_text = 'Archivo requerido'
            message_category = 'error'
        elif not _allowed_image(file.filename):
            message_text = 'Formato no permitido (solo JPG, PNG, WEBP)'
            message_category = 'error'
        else:
            base_static = current_app.config.get('STATIC_ROOT', None) or os.path.join(current_app.root_path, 'static')
            rel_dir = os.path.join('uploads', 'beauty_centers', center.slug)
            abs_dir = os.path.join(base_static, rel_dir)
            os.makedirs(abs_dir, exist_ok=True)

            ext = os.path.splitext(file.filename)[1].lower()
            fname = secure_filename(f"{uuid.uuid4().hex}{ext}")
            abs_path = os.path.join(abs_dir, fname)
            rel_path = os.path.join(rel_dir, fname).replace('\\', '/')

            try:
                file.save(abs_path)
                from app.models_catalog import BeautyCenterPhoto
                next_rank = (center.photos[-1].rank + 1) if center.photos else 0
                photo = BeautyCenterPhoto(beauty_center_id=center.id, path=rel_path, rank=next_rank)
                db.session.add(photo)
                db.session.commit()
                message_text = 'Foto subida correctamente'
                message_category = 'success'
            except Exception as e:
                current_app.logger.exception('Upload failed: %s', e)
                message_text = 'No se pudo subir la foto'
                message_category = 'error'

    return render_template('admin/partials/_beauty_photos.html', center=center, photos=center.photos,
                          message_text=message_text, message_category=message_category)


@bp.route('/beauty_photos/delete', methods=['POST'])
@login_required
def beauty_photos_delete():
    photo_id = request.form.get('photo_id', type=int)
    if not photo_id:
        return jsonify({'error': 'photo_id requerido'}), 400
    from app.models_catalog import BeautyCenterPhoto
    photo = BeautyCenterPhoto.query.get_or_404(photo_id)
    center = BeautyCenter.query.get_or_404(photo.beauty_center_id)

    allowed = False
    if current_user.is_superadmin:
        allowed = True
    else:
        link = db.session.execute(
            db.select(user_beauty_centers).where(
                user_beauty_centers.c.user_id == current_user.id,
                user_beauty_centers.c.beauty_center_id == center.id,
            )
        ).first()
        allowed = bool(link)
    if not allowed:
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        base_static = current_app.config.get('STATIC_ROOT', None) or os.path.join(current_app.root_path, 'static')
        abs_path = os.path.join(base_static, photo.path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except Exception as e:
        current_app.logger.warning('Could not delete photo file: %s', e)

    db.session.delete(photo)
    db.session.commit()

    return render_template('admin/partials/_beauty_photos.html', center=center, photos=center.photos,
                          message_text='Foto eliminada', message_category='success')


@bp.route('/beauty_settings')
@login_required
def beauty_settings():
    """HTMX partial listing beauty center public visibility settings."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    if current_user.is_superadmin:
        centers = BeautyCenter.query.order_by(BeautyCenter.name).all()
    else:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        centers = BeautyCenter.query.filter(BeautyCenter.id.in_(ids)).order_by(BeautyCenter.name).all() if ids else []

    return render_template('admin/partials/_beauty_settings.html', centers=centers)


@bp.route('/beauty_settings/update', methods=['POST'])
@login_required
def beauty_update_settings():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    center_id = request.form.get('center_id', type=int)
    show_public_booking = bool(request.form.get('show_public_booking'))
    booking_mode = (request.form.get('booking_mode') or 'flexible').strip()
    fixed_service_id = request.form.get('fixed_service_id', type=int)

    center = BeautyCenter.query.get_or_404(center_id)
    # Scope
    if not current_user.is_superadmin:
        link = db.session.execute(
            db.select(user_beauty_centers).where(
                user_beauty_centers.c.user_id == current_user.id,
                user_beauty_centers.c.beauty_center_id == center.id,
            )
        ).first()
        if not link:
            centers = []
            return render_template('admin/partials/_beauty_settings.html', centers=centers, message_text='Sin permisos para ese centro', message_category='error')


    center.show_public_booking = show_public_booking
    # Modo de reserva: solo superadmin puede cambiar booking_mode/fixed_service
    if current_user.is_superadmin:
        if booking_mode not in ('flexible', 'fixed'):
            booking_mode = 'flexible'
        center.booking_mode = booking_mode  # type: ignore[attr-defined]
        # Si es fijo, validar servicio seleccionado y alcance
        if center.booking_mode == 'fixed':  # type: ignore[attr-defined]
            # fixed_service_id opcional, pero si viene debe estar vinculado al centro
            if fixed_service_id:
                srv = Service.query.get(fixed_service_id)
                if not srv:
                    return jsonify({'error': 'Servicio fijo inválido'}), 400
                # Debe estar vinculado al centro
                linked = db.session.execute(
                    db.select(beauty_center_services).where(
                        beauty_center_services.c.beauty_center_id == center.id,
                        beauty_center_services.c.service_id == srv.id,
                    )
                ).first()
                if not linked:
                    return jsonify({'error': 'Servicio no vinculado al centro'}), 400
                center.fixed_service_id = srv.id  # type: ignore[attr-defined]
            else:
                center.fixed_service_id = None  # type: ignore[attr-defined]
        else:
            center.fixed_service_id = None  # type: ignore[attr-defined]
    db.session.commit()

    # Rerender
    if current_user.is_superadmin:
        centers = BeautyCenter.query.order_by(BeautyCenter.name).all()
    else:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        centers = BeautyCenter.query.filter(BeautyCenter.id.in_(ids)).order_by(BeautyCenter.name).all() if ids else []
    return render_template('admin/partials/_beauty_settings.html', centers=centers, message_text='Guardado', message_category='success')


@bp.route('/complex_settings')
@login_required
def complex_settings():
    """HTMX partial listing complexes public visibility settings (deportes)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403

    if current_user.is_superadmin:
        complexes = Complex.query.order_by(Complex.name).all()
    else:
        # complexes linked to user via UserComplex
        complexes = (
            Complex.query.join(UserComplex, UserComplex.complex_id == Complex.id)
            .filter(UserComplex.user_id == current_user.id)
            .order_by(Complex.name)
            .all()
        )

    return render_template('admin/partials/_complex_settings.html', complexes=complexes)


@bp.route('/complex_settings/update', methods=['POST'])
@login_required
def complex_update_settings():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403

    complex_id = request.form.get('complex_id', type=int)
    show_public_booking = bool(request.form.get('show_public_booking'))

    cpx = Complex.query.get_or_404(complex_id)
    # Scope
    if not current_user.is_superadmin:
        allowed = user_can_manage_complex(current_user, cpx.id)
        if not allowed:
            return jsonify({'error': 'Unauthorized'}), 403

    cpx.show_public_booking = show_public_booking
    db.session.commit()

    # Rerender
    if current_user.is_superadmin:
        complexes = Complex.query.order_by(Complex.name).all()
    else:
        complexes = (
            Complex.query.join(UserComplex, UserComplex.complex_id == Complex.id)
            .filter(UserComplex.user_id == current_user.id)
            .order_by(Complex.name)
            .all()
        )
    return render_template('admin/partials/_complex_settings.html', complexes=complexes, message_text='Guardado', message_category='success')


@bp.route('/field_settings')
@login_required
def field_settings():
    """HTMX partial listing fields per complex with public visibility toggle."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403

    # Load complexes in scope
    if current_user.is_superadmin:
        complexes = Complex.query.order_by(Complex.name).all()
    else:
        complexes = (
            Complex.query.join(UserComplex, UserComplex.complex_id == Complex.id)
            .filter(UserComplex.user_id == current_user.id)
            .order_by(Complex.name)
            .all()
        )

    return render_template('admin/partials/_field_settings.html', complexes=complexes)


@bp.route('/field_settings/update', methods=['POST'])
@login_required
def field_update_settings():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403

    field_id = request.form.get('field_id', type=int)
    show_public_booking = bool(request.form.get('show_public_booking'))

    f = Field.query.get_or_404(field_id)
    # Scope
    if not current_user.is_superadmin:
        allowed = user_can_manage_complex(current_user, f.complex_id)
        if not allowed:
            return jsonify({'error': 'Unauthorized'}), 403

    f.show_public_booking = show_public_booking
    db.session.commit()

    # Re-render
    if current_user.is_superadmin:
        complexes = Complex.query.order_by(Complex.name).all()
    else:
        complexes = (
            Complex.query.join(UserComplex, UserComplex.complex_id == Complex.id)
            .filter(UserComplex.user_id == current_user.id)
            .order_by(Complex.name)
            .all()
        )
    return render_template('admin/partials/_field_settings.html', complexes=complexes, message_text='Guardado', message_category='success')

@bp.route('/catalog_forms')
@login_required
@superadmin_required
def catalog_forms():
    return render_template(
        'admin/partials/_catalog_forms.html',
        prof_form=ProfessionalForm(),
        beauty_form=BeautyCenterForm(),
        sports_form=SportsComplexForm(),
    )


@bp.route('/catalog/create/<kind>', methods=['POST'])
@login_required
@superadmin_required
def catalog_create(kind):
    if kind == 'professional':
        form = ProfessionalForm()
        category_slug = 'profesionales'
        Model = Professional
        payload = {
            'name': form.name.data,
            'slug': form.slug.data,
            'city': form.city.data,
            'specialties': form.specialties.data,
            'address': form.address.data,
            'phone': form.phone.data,
            'website': form.website.data,
        }
    elif kind == 'beauty':
        form = BeautyCenterForm()
        category_slug = 'estetica'
        Model = BeautyCenter
        payload = {
            'name': form.name.data,
            'slug': form.slug.data,
            'city': form.city.data,
            'services': form.services.data,
            'address': form.address.data,
            'phone': form.phone.data,
            'website': form.website.data,
        }
    elif kind == 'sports':
        form = SportsComplexForm()
        category_slug = 'deportes'
        Model = SportsComplex
        payload = {
            'name': form.name.data,
            'slug': form.slug.data,
            'city': form.city.data,
            'sports': form.sports.data,
            'address': form.address.data,
            'phone': form.phone.data,
            'website': form.website.data,
        }
    else:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    if form.validate_on_submit():
        category = Category.query.filter_by(slug=category_slug).first()
        if not category:
            return jsonify({'success': False, 'message': 'Categoría no encontrada'}), 400
        obj = Model(**payload, category_id=category.id)
        db.session.add(obj)
        db.session.commit()
        flash('Creado correctamente', 'success')
        return redirect(url_for('admin.super_admin'))

    flash('Datos inválidos', 'error')
    return redirect(url_for('admin.super_admin'))


@bp.route('/link_services_form')
@login_required
@superadmin_required
def link_services_form():
    pros = Professional.query.order_by(Professional.name).limit(100).all()
    centers = BeautyCenter.query.order_by(BeautyCenter.name).limit(100).all()

    # Servicios por categoría
    serv_prof = Service.query.join(Category).filter(Category.slug == 'profesionales').order_by(Service.name).all()
    serv_beauty = Service.query.join(Category).filter(Category.slug == 'estetica').order_by(Service.name).all()

    return render_template(
        'admin/partials/_link_services.html',
        professionals=pros,
        centers=centers,
        services_prof=serv_prof,
        services_beauty=serv_beauty,
    )


@bp.route('/catalog/link_service', methods=['POST'])
@login_required
@superadmin_required
def catalog_link_service():
    kind = request.form.get('kind')
    entity_id = request.form.get('entity_id', type=int)
    service_id = request.form.get('service_id', type=int)
    center_id = request.form.get('center_id', type=int)

    if not kind or not entity_id or not service_id:
        return jsonify({'success': False, 'message': 'Parámetros inválidos'}), 400

    service = Service.query.get_or_404(service_id)

    if kind == 'professional':
        entity = Professional.query.get_or_404(entity_id)
        # Validar categoría
        if entity.category and service.category_id != entity.category_id:
            return jsonify({'success': False, 'message': 'El servicio no coincide con la categoría del profesional'}), 400
        if service not in entity.linked_services:
            entity.linked_services.append(service)
    elif kind == 'beauty':
        entity = BeautyCenter.query.get_or_404(entity_id)
        if entity.category and service.category_id != entity.category_id:
            return jsonify({'success': False, 'message': 'El servicio no coincide con la categoría del centro'}), 400
        if service not in entity.linked_services:
            entity.linked_services.append(service)
    else:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    db.session.commit()
    flash('Servicio vinculado correctamente', 'success')
    return redirect(url_for('admin.super_admin'))


@bp.route('/catalog/unlink_service', methods=['POST'])
@login_required
@superadmin_required
def catalog_unlink_service():
    kind = request.form.get('kind')
    entity_id = request.form.get('entity_id', type=int)
    service_id = request.form.get('service_id', type=int)

    if not kind or not entity_id or not service_id:
        return jsonify({'success': False, 'message': 'Parámetros inválidos'}), 400

    service = Service.query.get_or_404(service_id)

    if kind == 'professional':
        entity = Professional.query.get_or_404(entity_id)
        if service in entity.linked_services:
            entity.linked_services.remove(service)
    elif kind == 'beauty':
        entity = BeautyCenter.query.get_or_404(entity_id)
        if service in entity.linked_services:
            entity.linked_services.remove(service)
    else:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    db.session.commit()
    flash('Servicio desvinculado', 'info')
    return redirect(url_for('admin.super_admin'))

@bp.route('/turnos_table')
@login_required
def turnos_table():
    """HTMX partial for admin turnos table"""
    # Get and validate parameters
    date_str = request.args.get('date', '')
    span = request.args.get('span', 'day')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    complex_slug = request.args.get('complex_slug', '')
    sport_service = request.args.get('sport_service', '')
    page = int(request.args.get('page', 1))
    focus_id = request.args.get('focus_id', type=int)
    token = request.args.get('t')
    token_invalid = False

    # If a token is provided, verify and derive focus_id
    if token and not focus_id:
        try:
            s = URLSafeTimedSerializer(current_app.secret_key, salt='admin-focus')
            ttl = int(current_app.config.get('FOCUS_TOKEN_TTL', 7200))
            data = s.loads(token, max_age=ttl)
            focus_id = int(data.get('ts')) if isinstance(data, dict) else None
        except (BadSignature, SignatureExpired, Exception):
            focus_id = None
            token_invalid = True
    limit = min(int(request.args.get('limit', 20)), 50)
    
    # Build base query - limit to the admin's own scope
    if current_user.is_superadmin:
        query = Timeslot.query
    else:
        user_category = getattr(getattr(current_user, 'category', None), 'slug', None)
        if user_category == 'deportes':
            user_complexes = db.session.query(UserComplex.complex_id).filter_by(user_id=current_user.id).subquery()
            query = Timeslot.query.join(Field).filter(Field.complex_id.in_(user_complexes))
        elif user_category == 'profesionales':
            # services linked to the user's professionals
            prof_ids_sq = db.select(user_professionals.c.professional_id).where(
                user_professionals.c.user_id == current_user.id
            ).subquery()
            service_ids_sq = db.select(professional_services.c.service_id).where(
                professional_services.c.professional_id.in_(db.select(prof_ids_sq))
            )
            query = Timeslot.query.filter(Timeslot.service_id.in_(service_ids_sq))
        elif user_category == 'estetica':
            # services linked to the user's beauty centers
            bc_ids_sq = db.select(user_beauty_centers.c.beauty_center_id).where(
                user_beauty_centers.c.user_id == current_user.id
            ).subquery()
            service_ids_sq = db.select(beauty_center_services.c.service_id).where(
                beauty_center_services.c.beauty_center_id.in_(db.select(bc_ids_sq))
            )
            query = Timeslot.query.filter(Timeslot.service_id.in_(service_ids_sq))
        else:
            # No category → no results
            query = Timeslot.query.filter(db.text('1=0'))
    
    # Date filter
    if date_str and validate_date_format(date_str):
        try:
            if span == 'week':
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                days_since_monday = target_date.weekday()
                week_start = target_date - timedelta(days=days_since_monday)
                week_end = week_start + timedelta(days=7)
                query = query.filter(
                    and_(
                        Timeslot.start >= week_start,
                        Timeslot.start < week_end
                    )
                )
            else:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                query = query.filter(
                    and_(
                        Timeslot.start >= target_date,
                        Timeslot.start < target_date + timedelta(days=1)
                    )
                )
        except ValueError:
            current_app.logger.debug("Invalid date format for 'date' in admin.turnos_table: %s", date_str)
    
    # Category filter
    if category and validate_category(category):
        if category == 'deportes':
            query = query.join(Field).join(Complex).join(Complex.categories).filter(Category.slug == category)
        else:
            query = query.join(Service).join(Category).filter(Category.slug == category)
    
    # Status filter
    if status and validate_status(status):
        query = query.filter(Timeslot.status == TimeslotStatus(status))
    
    # Complex filter (solo aplica a deportes)
    if complex_slug and ((category == 'deportes') or (not category and getattr(getattr(current_user, 'category', None), 'slug', None) == 'deportes')):
        complex_slug = clean_text(complex_slug, 200)
        query = query.join(Field).join(Complex).filter(Complex.slug.ilike(f'%{complex_slug}%'))
    
    # Sport/Service filter
    if sport_service:
        sport_service = clean_text(sport_service, 100)
        if category == 'deportes':
            query = query.join(Field).filter(Field.sport.ilike(f'%{sport_service}%'))
        else:
            query = query.join(Service).filter(Service.name.ilike(f'%{sport_service}%'))
    
    # Exclude past timeslots (only show those starting after now), unless focusing
    now = datetime.now(timezone.utc)
    if not focus_id:
        query = query.filter(Timeslot.start > now)

    # Focus on a specific timeslot if requested and within scope
    if focus_id:
        query = query.filter(Timeslot.id == focus_id)

    # Order and paginate
    query = query.order_by(Timeslot.start)
    total = query.count()
    offset = (page - 1) * limit
    timeslots = query.offset(offset).limit(limit).all()

    # Lazy-expire HOLDING timeslots if Redis TTL key is missing
    changed = False
    try:
        for t in timeslots:
            if getattr(t, 'status', None) == TimeslotStatus.HOLDING:
                key = f"hold:timeslot:{t.id}"
                if not current_app.redis.get(key):
                    t.status = TimeslotStatus.AVAILABLE
                    t.reservation_code = None
                    changed = True
        if changed:
            db.session.commit()
    except Exception as _e:
        current_app.logger.warning(f"Lazy expire holds (admin) failed: {_e}")
    
    # Calculate pagination info
    has_next = total > (page * limit)
    has_prev = page > 1
    
    notice_text = None
    notice_category = None
    if token_invalid:
        notice_text = 'El enlace directo expiró o no es válido. Usa filtros o busca el turno.'
        notice_category = 'error'

    return render_template('admin/partials/_admin_turnos_table.html', 
                          timeslots=timeslots,
                          page=page,
                          has_next=has_next,
                          has_prev=has_prev,
                          total=total,
                          notice_text=notice_text,
                          notice_category=notice_category)

# Super Admin Routes
@bp.route('/categories_table')
@login_required
@superadmin_required
def categories_table():
    """HTMX partial for categories management"""
    categories = Category.query.all()
    return render_template('admin/partials/_categories_table.html', categories=categories)

@bp.route('/services_table')
@login_required
@superadmin_required
def services_table():
    """HTMX partial for services management"""
    services = Service.query.join(Category).all()
    return render_template('admin/partials/_services_table.html', services=services)

@bp.route('/complexes_table')
@login_required
@superadmin_required
def complexes_table():
    """HTMX partial for complexes management"""
    complexes = Complex.query.all()
    return render_template('admin/partials/_complexes_table.html', complexes=complexes)


# Estética: creación de servicios por administradores
@bp.route('/services/create_form')
@login_required
def services_create_form():
    """Parcial HTMX para crear servicios de Estética.

    Permite a admins de centros de estética (o superadmin) definir servicios
    con duración personalizada (ej.: corte 30 min, coloración 90 min).
    """
    # Solo disponible para superadmin o usuarios con categoría 'estetica'
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    return render_template('admin/partials/_service_create_form.html')


@bp.route('/services/create', methods=['POST'])
@login_required
def services_create():
    """Crea un nuevo Service para la categoría Estética.

    Seguridad:
    - Requiere CSRF (via template)
    - Requiere admin con categoría 'estetica' o superadmin
    - Valida nombre/slug, duración (15-360), y unicidad de slug por categoría
    - Anti-IDOR: al vincular, solo se asocia a centros del usuario actual
    """
    # Autorización
    is_estetica_admin = bool(getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')
    if not (current_user.is_superadmin or is_estetica_admin):
        return jsonify({'error': 'Unauthorized'}), 403

    # Datos y sanitización
    name = clean_text(request.form.get('name', ''), 200)
    slug = clean_text((request.form.get('slug', '') or '').lower(), 180)
    duration_min = request.form.get('duration_min', type=int)
    price_raw = (request.form.get('base_price') or '').strip()
    currency = clean_text(request.form.get('currency', 'ARS'), 3) or 'ARS'

    message_text = ''
    message_category = 'success'

    # Validaciones básicas
    import re
    if not name or not slug:
        message_text = 'Nombre y slug son requeridos'
        message_category = 'error'
    elif not re.match(r'^[a-z0-9\-]+$', slug):
        message_text = 'El slug solo puede contener a-z, 0-9 y guiones (-)'
        message_category = 'error'
    elif not duration_min or duration_min < 15 or duration_min > 360:
        message_text = 'Duración inválida (15–360 minutos)'
        message_category = 'error'

    # Resolver categoría Estética
    category = None
    if message_category == 'success':
        category = Category.query.filter_by(slug='estetica').first()
        if not category:
            message_text = 'Categoría Estética no configurada'
            message_category = 'error'

    # Precio opcional
    base_price = None
    if message_category == 'success' and price_raw:
        try:
            norm = price_raw.replace(',', '.')
            base_price = float(norm)
            if base_price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio base inválido'
            message_category = 'error'

    # Unicidad slug por categoría
    if message_category == 'success':
        exists = Service.query.filter_by(category_id=category.id, slug=slug).first()
        if exists:
            message_text = 'Ya existe un servicio con ese slug en Estética'
            message_category = 'error'

    # Crear servicio
    created = None
    if message_category == 'success':
        created = Service(
            category_id=category.id,
            name=name,
            slug=slug,
            duration_min=duration_min,
            base_price=base_price,
            currency=currency or 'ARS',
            is_active=True,
        )
        db.session.add(created)
        db.session.flush()

        # Vincular automáticamente a centros de estética del usuario
        try:
            if is_estetica_admin and hasattr(current_user, 'beauty_centers'):
                centers = list(current_user.beauty_centers)  # dynamic -> list
                if centers:
                    # Import aquí para evitar ciclos
                    from app.models_catalog import BeautyCenter  # noqa: F401
                    for bc in centers:
                        if created not in bc.linked_services:
                            bc.linked_services.append(created)
        except Exception:
            # No bloquear la creación por vínculos; seguir
            current_app.logger.exception('Error vinculando servicio a centros del usuario')

        db.session.commit()
        message_text = f'Servicio "{escape(name)}" creado correctamente'

    return render_template(
        'admin/partials/_service_create_form.html',
        message_text=message_text,
        message_category=message_category,
    )


# Profesionales: creación de turnos por servicio
@bp.route('/timeslots/service_create_form')
@login_required
def timeslots_service_create_form():
    """Parcial HTMX con formulario para crear turnos (profesionales por servicio)."""
    # Autorización: superadmin o usuario con categoría 'profesionales'
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    # Profesionales disponibles para el usuario
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        # IDs vinculados al usuario vía tabla puente
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []

    return render_template('admin/partials/_timeslot_service_create_form.html', professionals=professionals)


@bp.route('/timeslots/services_options')
@login_required
def timeslot_services_options():
    """Devuelve <option> para combo de servicios según profesional (HTMX)."""
    prof_id = request.args.get('professional_id', type=int)
    if not prof_id:
        return render_template('admin/partials/_options.html', options=[])

    prof = Professional.query.get_or_404(prof_id)

    # Autorización: superadmin o vinculado
    if not current_user.is_superadmin:
        link = db.session.execute(
            db.select(user_professionals).where(
                user_professionals.c.user_id == current_user.id,
                user_professionals.c.professional_id == prof.id,
            )
        ).first()
        if not link:
            return jsonify({'error': 'Unauthorized'}), 403

    # Solo servicios de categoría 'profesionales' vinculados al profesional
    services = [s for s in prof.linked_services if s.category and s.category.slug == 'profesionales' and s.is_active]
    services = sorted(services, key=lambda s: (s.name or '').lower())
    return render_template('admin/partials/_options.html', options=[(s.id, f"{s.name} ({s.duration_min} min)") for s in services])


@bp.route('/timeslots/create_for_service', methods=['POST'])
@login_required
def timeslots_create_for_service():
    """Crea un turno para un servicio seleccionado (panel de profesionales).

    - CSRF requerido (via hidden input en template)
    - Autorización: superadmin o usuario vinculado al profesional
    - Valida fecha futura, usa duración del servicio, evita solapes por servicio
    """
    professional_id = request.form.get('professional_id', type=int)
    service_id = request.form.get('service_id', type=int)
    start_str = (request.form.get('start') or '').strip()
    price_raw = (request.form.get('price') or '').strip()

    message_text = ''
    message_category = 'success'

    # Entidades
    prof = Professional.query.get(professional_id) if professional_id else None
    srv = Service.query.get(service_id) if service_id else None

    if not prof:
        message_text = 'Profesional inválido'
        message_category = 'error'
    elif not srv or not srv.is_active:
        message_text = 'Servicio inválido'
        message_category = 'error'

    # Autorización y vínculo profesional-servicio
    if message_category == 'success':
        if not current_user.is_superadmin:
            link = db.session.execute(
                db.select(user_professionals).where(
                    user_professionals.c.user_id == current_user.id,
                    user_professionals.c.professional_id == prof.id,
                )
            ).first()
            if not link:
                return jsonify({'error': 'Unauthorized'}), 403
        if srv not in prof.linked_services or not (srv.category and srv.category.slug == 'profesionales'):
            message_text = 'El servicio no está vinculado al profesional'
            message_category = 'error'

    # Parseo de fecha
    start_dt = None
    if message_category == 'success':
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
        except Exception:
            message_text = 'Fecha y hora de inicio inválidas'
            message_category = 'error'

    # Futura
    if message_category == 'success':
        now = datetime.now(timezone.utc)
        if start_dt <= now:
            message_text = 'La hora de inicio debe ser futura'
            message_category = 'error'

    # Calcular fin con duración del servicio
    end_dt = None
    if message_category == 'success':
        duration_min = int(srv.duration_min or 0)
        if duration_min < 15 or duration_min > 360:
            message_text = 'Duración de servicio inválida'
            message_category = 'error'
        else:
            end_dt = start_dt + timedelta(minutes=duration_min)

    # Precio opcional
    price = None
    if message_category == 'success' and price_raw:
        try:
            price = float(price_raw.replace(',', '.'))
            if price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio inválido'
            message_category = 'error'

    # Evitar solapamiento en el mismo servicio
    if message_category == 'success':
        overlap = (
            Timeslot.query
            .filter(
                Timeslot.service_id == srv.id,
                Timeslot.beauty_center_id == center.id,
                Timeslot.start < end_dt,
                Timeslot.end > start_dt,
            )
            .first()
        )
        if overlap:
            message_text = 'Existe un turno que se solapa para este servicio'
            message_category = 'error'

    # Crear turno
    if message_category == 'success':
        t = Timeslot(
            service_id=srv.id,
            beauty_center_id=center.id,
            start=start_dt,
            end=end_dt,
            price=price,
            currency=srv.currency or 'ARS',
            status=TimeslotStatus.AVAILABLE,
        )
        db.session.add(t)
        db.session.commit()
        message_text = 'Turno creado correctamente'

    # Re-render parcial
    # Reusar el form original con lista de profesionales disponible
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []

    return render_template(
        'admin/partials/_timeslot_service_create_form.html',
        professionals=professionals,
        message_text=message_text,
        message_category=message_category,
    )


# Profesionales: listado de servicios vinculados al usuario (Mis Servicios)
@bp.route('/my_services_table')
@login_required
def my_services_table():
    """HTMX partial con servicios de profesionales vinculados al admin actual."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    # Obtener profesionales vinculados
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []

    # Agregar servicios únicos (solo categoría profesionales)
    services = []
    seen = set()
    for p in professionals:
        for s in p.linked_services:
            if not s.is_active or not s.category or s.category.slug != 'profesionales':
                continue
            if s.id in seen:
                continue
            seen.add(s.id)
            services.append(s)

    services = sorted(services, key=lambda s: (s.name or '').lower())
    return render_template('admin/partials/_my_services_table.html', services=services)


@bp.route('/my_services/toggle', methods=['POST'])
@login_required
def my_services_toggle():
    """Activa/Desactiva un servicio del alcance del admin (profesionales)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.form.get('service_id', type=int)
    srv = Service.query.get_or_404(service_id)

    # Verificar alcance
    in_scope = False
    if current_user.is_superadmin:
        in_scope = True
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        if ids:
            # ¿Algún profesional del usuario tiene este servicio?
            linked = db.session.execute(
                db.select(professional_services).where(
                    professional_services.c.professional_id.in_(ids),
                    professional_services.c.service_id == srv.id,
                )
            ).first()
            in_scope = bool(linked)
    if not in_scope:
        return jsonify({'error': 'Unauthorized'}), 403

    srv.is_active = not bool(srv.is_active)
    db.session.commit()

    # Reusar tabla
    return my_services_table()


@bp.route('/timeslots/quick_form')
@login_required
def timeslots_quick_form():
    """Parcial con formulario rápido para crear turno por servicio (profesionales)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.args.get('service_id', type=int)
    srv = Service.query.get_or_404(service_id)

    # Profesionales disponibles que ofrecen este servicio
    if current_user.is_superadmin:
        professionals = (
            Professional.query
            .join(professional_services, professional_services.c.professional_id == Professional.id)
            .filter(professional_services.c.service_id == srv.id)
            .order_by(Professional.name)
            .all()
        )
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = (
            Professional.query
            .join(professional_services, professional_services.c.professional_id == Professional.id)
            .filter(
                Professional.id.in_(ids) if ids else db.text('1=0'),
                professional_services.c.service_id == srv.id,
            )
            .order_by(Professional.name)
            .all()
        )

    return render_template('admin/partials/_quick_timeslot_form.html', service=srv, professionals=professionals)


@bp.route('/timeslots/create_for_service_quick', methods=['POST'])
@login_required
def timeslots_create_for_service_quick():
    """Crea turno rápido y refresca 'Mis Servicios'."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    professional_id = request.form.get('professional_id', type=int)
    service_id = request.form.get('service_id', type=int)
    start_str = (request.form.get('start') or '').strip()
    price_raw = (request.form.get('price') or '').strip()

    message_text = ''
    message_category = 'success'

    prof = Professional.query.get(professional_id) if professional_id else None
    srv = Service.query.get(service_id) if service_id else None

    if not prof or not srv or not srv.is_active:
        message_text = 'Datos inválidos'
        message_category = 'error'

    # Alcance usuario
    if message_category == 'success' and not current_user.is_superadmin:
        link = db.session.execute(
            db.select(user_professionals).where(
                user_professionals.c.user_id == current_user.id,
                user_professionals.c.professional_id == prof.id,
            )
        ).first()
        if not link:
            return jsonify({'error': 'Unauthorized'}), 403
        if srv not in prof.linked_services:
            message_text = 'El servicio no está vinculado al profesional'
            message_category = 'error'

    # Parse fecha
    start_dt = None
    if message_category == 'success':
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
        except Exception:
            message_text = 'Fecha/hora inválida'
            message_category = 'error'

    # Futuro
    if message_category == 'success':
        if start_dt <= datetime.now(timezone.utc):
            message_text = 'La hora de inicio debe ser futura'
            message_category = 'error'

    # Fin
    end_dt = None
    if message_category == 'success':
        duration_min = int(srv.duration_min or 0)
        if duration_min < 15 or duration_min > 360:
            message_text = 'Duración de servicio inválida'
            message_category = 'error'
        else:
            end_dt = start_dt + timedelta(minutes=duration_min)

    # Precio
    price = None
    if message_category == 'success' and price_raw:
        try:
            price = float(price_raw.replace(',', '.'))
            if price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio inválido'
            message_category = 'error'

    # Solape
    if message_category == 'success':
        overlap = (
            Timeslot.query
            .filter(
                Timeslot.service_id == srv.id,
                Timeslot.start < end_dt,
                Timeslot.end > start_dt,
            )
            .first()
        )
        if overlap:
            message_text = 'Existe un turno que se solapa para este servicio'
            message_category = 'error'

    if message_category == 'success':
        t = Timeslot(
            service_id=srv.id,
            start=start_dt,
            end=end_dt,
            price=price,
            currency=srv.currency or 'ARS',
            status=TimeslotStatus.AVAILABLE,
        )
        db.session.add(t)
        db.session.commit()
        message_text = 'Turno creado correctamente'

    # Re-render tabla con mensaje (si aplicara, se puede pasar via flash o contexto)
    # Reconstruir servicios como en my_services_table
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []

    services = []
    seen = set()
    for p in professionals:
        for s in p.linked_services:
            if not s.category or s.category.slug != 'profesionales':
                continue
            if s.id in seen:
                continue
            seen.add(s.id)
            services.append(s)
    services = sorted(services, key=lambda s: (s.name or '').lower())

    return render_template('admin/partials/_my_services_table.html', services=services, message_text=message_text, message_category=message_category)


# Estética: listado de servicios vinculados al usuario (Mis Servicios)
@bp.route('/my_beauty_services_table')
@login_required
def my_beauty_services_table():
    """HTMX partial con servicios de estética vinculados a los centros del admin actual."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    # Centros vinculados
    if current_user.is_superadmin:
        centers = BeautyCenter.query.order_by(BeautyCenter.name).all()
    else:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        centers = BeautyCenter.query.filter(BeautyCenter.id.in_(ids)).order_by(BeautyCenter.name).all() if ids else []

    services = []
    seen: set[int] = set()
    allowed_service_ids: set[int] = set()
    for c in centers:
        # Calcular servicios permitidos según modo del centro
        if getattr(c, 'booking_mode', 'flexible') == 'fixed' and getattr(c, 'fixed_service_id', None):
            allowed_service_ids.add(int(c.fixed_service_id))  # type: ignore[arg-type]
        else:
            for s in c.linked_services:
                if s.category and s.category.slug == 'estetica':
                    allowed_service_ids.add(s.id)
        # Armar listado de servicios visibles (solo los permitidos si hay restricción)
        for s in c.linked_services:
            if not s.category or s.category.slug != 'estetica':
                continue
            if allowed_service_ids and s.id not in allowed_service_ids:
                continue
            if s.id in seen:
                continue
            seen.add(s.id)
            services.append(s)
    services = sorted(services, key=lambda s: (s.name or '').lower())
    return render_template('admin/partials/_my_services_beauty_table.html', services=services, allowed_service_ids=allowed_service_ids)


# ----- Edición inline de servicios (Profesionales) -----
@bp.route('/my_services/edit_form')
@login_required
def my_services_edit_form():
    """Devuelve formulario inline para editar duración/precio de un servicio (profesionales)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.args.get('service_id', type=int)
    srv = Service.query.get_or_404(service_id)

    # Verificar alcance: vinculación con algún profesional del usuario y categoría correcta
    in_scope = False
    if current_user.is_superadmin:
        in_scope = True
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        if ids and srv.category and srv.category.slug == 'profesionales':
            linked = db.session.execute(
                db.select(professional_services).where(
                    professional_services.c.professional_id.in_(ids),
                    professional_services.c.service_id == srv.id,
                )
            ).first()
            in_scope = bool(linked)
    if not in_scope:
        return jsonify({'error': 'Unauthorized'}), 403

    return render_template('admin/partials/_service_inline_edit_prof.html', service=srv)


@bp.route('/my_services/update', methods=['POST'])
@login_required
def my_services_update():
    """Actualiza duración y precio base de un servicio en profesionales."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'profesionales')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.form.get('service_id', type=int)
    duration_min = request.form.get('duration_min', type=int)
    price_raw = (request.form.get('base_price') or '').strip()
    currency = clean_text(request.form.get('currency', 'ARS'), 3) or 'ARS'

    message_text = ''
    message_category = 'success'

    srv = Service.query.get(service_id) if service_id else None
    if not srv or not (srv.category and srv.category.slug == 'profesionales'):
        message_text = 'Servicio inválido'
        message_category = 'error'

    # Validación de centro
    center = None
    if message_category == 'success':
        center = BeautyCenter.query.get(center_id) if center_id else None
        if not center:
            message_text = 'Centro requerido'
            message_category = 'error'

    # Alcance
    if message_category == 'success' and not current_user.is_superadmin:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        linked = None
        if ids:
            linked = db.session.execute(
                db.select(professional_services).where(
                    professional_services.c.professional_id.in_(ids),
                    professional_services.c.service_id == srv.id,
                )
            ).first()
        if not linked:
            return jsonify({'error': 'Unauthorized'}), 403

    # Validaciones
    if message_category == 'success':
        if not duration_min or duration_min < 15 or duration_min > 360:
            message_text = 'Duración inválida (15–360)'
            message_category = 'error'

    base_price = None
    if message_category == 'success' and price_raw:
        try:
            base_price = float(price_raw.replace(',', '.'))
            if base_price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio base inválido'
            message_category = 'error'

    # Persistir
    if message_category == 'success':
        srv.duration_min = duration_min
        srv.base_price = base_price
        srv.currency = currency
        db.session.commit()
        message_text = 'Servicio actualizado'

    # Refrescar tabla
    # Reusar my_services_table pero inyectando mensajes
    # reconstrucción como en my_services_table
    if current_user.is_superadmin:
        professionals = Professional.query.order_by(Professional.name).all()
    else:
        rows = db.session.execute(
            db.select(user_professionals.c.professional_id).where(user_professionals.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        professionals = Professional.query.filter(Professional.id.in_(ids)).order_by(Professional.name).all() if ids else []

    services = []
    seen = set()
    for p in professionals:
        for s in p.linked_services:
            if not s.is_active or not s.category or s.category.slug != 'profesionales':
                continue
            if s.id in seen:
                continue
            seen.add(s.id)
            services.append(s)
    services = sorted(services, key=lambda s: (s.name or '').lower())
    return render_template('admin/partials/_my_services_table.html', services=services, message_text=message_text, message_category=message_category)


# ----- Edición inline de servicios (Estética) -----
@bp.route('/my_beauty_services/edit_form')
@login_required
def my_beauty_services_edit_form():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.args.get('service_id', type=int)
    srv = Service.query.get_or_404(service_id)

    in_scope = False
    if current_user.is_superadmin:
        in_scope = True
    else:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        if ids and srv.category and srv.category.slug == 'estetica':
            linked = db.session.execute(
                db.select(beauty_center_services).where(
                    beauty_center_services.c.beauty_center_id.in_(ids),
                    beauty_center_services.c.service_id == srv.id,
                )
            ).first()
            in_scope = bool(linked)
    if not in_scope:
        return jsonify({'error': 'Unauthorized'}), 403

    return render_template('admin/partials/_service_inline_edit_beauty.html', service=srv)


@bp.route('/my_beauty_services/update', methods=['POST'])
@login_required
def my_beauty_services_update():
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.form.get('service_id', type=int)
    duration_min = request.form.get('duration_min', type=int)
    price_raw = (request.form.get('base_price') or '').strip()
    currency = clean_text(request.form.get('currency', 'ARS'), 3) or 'ARS'

    message_text = ''
    message_category = 'success'

    srv = Service.query.get(service_id) if service_id else None
    if not srv or not (srv.category and srv.category.slug == 'estetica'):
        message_text = 'Servicio inválido'
        message_category = 'error'

    if message_category == 'success' and not current_user.is_superadmin:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        linked = None
        if ids:
            linked = db.session.execute(
                db.select(beauty_center_services).where(
                    beauty_center_services.c.beauty_center_id.in_(ids),
                    beauty_center_services.c.service_id == srv.id,
                )
            ).first()
        if not linked:
            return jsonify({'error': 'Unauthorized'}), 403

    if message_category == 'success':
        if not duration_min or duration_min < 15 or duration_min > 360:
            message_text = 'Duración inválida (15–360)'
            message_category = 'error'

    base_price = None
    if message_category == 'success' and price_raw:
        try:
            base_price = float(price_raw.replace(',', '.'))
            if base_price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio base inválido'
            message_category = 'error'

    if message_category == 'success':
        srv.duration_min = duration_min
        srv.base_price = base_price
        srv.currency = currency
        db.session.commit()
        message_text = 'Servicio actualizado'

    # Refrescar tabla estética
    return my_beauty_services_table()


@bp.route('/my_beauty_services/toggle', methods=['POST'])
@login_required
def my_beauty_services_toggle():
    """Activa/Desactiva un servicio en el alcance de estética del admin."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.form.get('service_id', type=int)
    srv = Service.query.get_or_404(service_id)

    in_scope = False
    if current_user.is_superadmin:
        in_scope = True
    else:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        if ids:
            linked = db.session.execute(
                db.select(beauty_center_services).where(
                    beauty_center_services.c.beauty_center_id.in_(ids),
                    beauty_center_services.c.service_id == srv.id,
                )
            ).first()
            in_scope = bool(linked)
    if not in_scope:
        return jsonify({'error': 'Unauthorized'}), 403

    srv.is_active = not bool(srv.is_active)
    db.session.commit()
    return my_beauty_services_table()


@bp.route('/timeslots/quick_form_beauty')
@login_required
def timeslots_quick_form_beauty():
    """Parcial rápido para crear turno por servicio (estética)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.args.get('service_id', type=int)
    srv = Service.query.get_or_404(service_id)

    # Verificar que el servicio esté en alcance (algún centro del usuario)
    if not current_user.is_superadmin:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        if ids:
            linked = db.session.execute(
                db.select(beauty_center_services).where(
                    beauty_center_services.c.beauty_center_id.in_(ids),
                    beauty_center_services.c.service_id == srv.id,
                )
            ).first()
            if not linked:
                return jsonify({'error': 'Unauthorized'}), 403
        else:
            return jsonify({'error': 'Unauthorized'}), 403

    # Centros disponibles para este servicio según alcance
    if current_user.is_superadmin:
        centers = (
            BeautyCenter.query
            .join(beauty_center_services, beauty_center_services.c.beauty_center_id == BeautyCenter.id)
            .filter(beauty_center_services.c.service_id == srv.id)
            .order_by(BeautyCenter.name)
            .all()
        )
    else:
        rows = db.session.execute(
            db.select(user_beauty_centers.c.beauty_center_id).where(user_beauty_centers.c.user_id == current_user.id)
        ).all()
        ids = [r[0] for r in rows]
        centers = (
            BeautyCenter.query
            .join(beauty_center_services, beauty_center_services.c.beauty_center_id == BeautyCenter.id)
            .filter(
                BeautyCenter.id.in_(ids) if ids else db.text('1=0'),
                beauty_center_services.c.service_id == srv.id,
            )
            .order_by(BeautyCenter.name)
            .all()
        )

    # Si el centro está en modo fijo, solo permitir el servicio fijo
    centers = [
        c for c in centers
        if (getattr(c, 'booking_mode', 'flexible') != 'fixed') or (getattr(c, 'fixed_service_id', None) == srv.id)
    ]

    return render_template('admin/partials/_quick_timeslot_form_beauty.html', service=srv, centers=centers)


@bp.route('/timeslots/create_for_service_quick_beauty', methods=['POST'])
@login_required
def timeslots_create_for_service_quick_beauty():
    """Crea turno rápido para estética y refresca 'Mis Servicios (Estética)'."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'estetica')):
        return jsonify({'error': 'Unauthorized'}), 403

    service_id = request.form.get('service_id', type=int)
    center_id = request.form.get('center_id', type=int)
    start_str = (request.form.get('start') or '').strip()
    price_raw = (request.form.get('price') or '').strip()

    message_text = ''
    message_category = 'success'

    srv = Service.query.get(service_id) if service_id else None
    center = BeautyCenter.query.get(center_id) if center_id else None
    if not srv or not srv.is_active:
        message_text = 'Servicio inválido'
        message_category = 'error'
    if message_category == 'success' and not center:
        message_text = 'Centro requerido'
        message_category = 'error'

    # Alcance
    if message_category == 'success':
        if current_user.is_superadmin:
            linked = db.session.execute(
                db.select(beauty_center_services).where(
                    beauty_center_services.c.beauty_center_id == center.id,
                    beauty_center_services.c.service_id == srv.id,
                )
            ).first()
            if not linked:
                message_text = 'El servicio no está vinculado al centro'
                message_category = 'error'
        else:
            link_user = db.session.execute(
                db.select(user_beauty_centers).where(
                    user_beauty_centers.c.user_id == current_user.id,
                    user_beauty_centers.c.beauty_center_id == center.id,
                )
            ).first()
            link_srv = db.session.execute(
                db.select(beauty_center_services).where(
                    beauty_center_services.c.beauty_center_id == center.id,
                    beauty_center_services.c.service_id == srv.id,
                )
            ).first()
            if not (link_user and link_srv):
                return jsonify({'error': 'Unauthorized'}), 403

    # Si el centro es fijo, el servicio debe coincidir
    if message_category == 'success':
        if getattr(center, 'booking_mode', 'flexible') == 'fixed':
            if getattr(center, 'fixed_service_id', None) != srv.id:
                message_text = 'Centro en modo fijo: servicio no permitido'
                message_category = 'error'

    # Parse fecha
    start_dt = None
    if message_category == 'success':
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
        except Exception:
            message_text = 'Fecha/hora inválida'
            message_category = 'error'

    # Futuro
    if message_category == 'success' and start_dt <= datetime.now(timezone.utc):
        message_text = 'La hora de inicio debe ser futura'
        message_category = 'error'

    # Fin
    end_dt = None
    if message_category == 'success':
        duration_min = int(srv.duration_min or 0)
        if duration_min < 15 or duration_min > 360:
            message_text = 'Duración de servicio inválida'
            message_category = 'error'
        else:
            end_dt = start_dt + timedelta(minutes=duration_min)

    # Precio
    price = None
    if message_category == 'success' and price_raw:
        try:
            price = float(price_raw.replace(',', '.'))
            if price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio inválido'
            message_category = 'error'

    # Solape
    if message_category == 'success':
        overlap = (
            Timeslot.query
            .filter(
                Timeslot.service_id == srv.id,
                Timeslot.start < end_dt,
                Timeslot.end > start_dt,
            )
            .first()
        )
        if overlap:
            message_text = 'Existe un turno que se solapa para este servicio'
            message_category = 'error'

    if message_category == 'success':
        t = Timeslot(
            service_id=srv.id,
            beauty_center_id=center.id if center else None,
            start=start_dt,
            end=end_dt,
            price=price,
            currency=srv.currency or 'ARS',
            status=TimeslotStatus.AVAILABLE,
        )
        db.session.add(t)
        db.session.commit()
        message_text = 'Turno creado correctamente'

    # Reconstruir tabla de servicios estética
    return my_beauty_services_table()

@bp.route('/complexes/create', methods=['POST'])
@login_required
@superadmin_required
def complexes_create():
    """Create a new Complex from Superadmin panel (HTMX-friendly)."""
    # Sanitize inputs
    name = clean_text(request.form.get('name', ''), 200)
    slug = clean_text(request.form.get('slug', ''), 200).lower()
    city = clean_text(request.form.get('city', ''), 100)
    address = clean_text(request.form.get('address', ''), 200)
    contact_phone = clean_text(request.form.get('contact_phone', ''), 50)
    contact_email = (request.form.get('contact_email') or '').strip().lower()

    message_text = ''
    message_category = 'success'

    # Basic validation
    if not name or not slug or not city:
        message_text = 'Nombre, slug y ciudad son requeridos'
        message_category = 'error'
    else:
        # Validate slug format and uniqueness
        import re
        if not re.match(r'^[a-z0-9\-]+$', slug):
            message_text = 'El slug solo puede contener a-z, 0-9 y guiones (-)'
            message_category = 'error'
        else:
            existing = Complex.query.filter_by(slug=slug).first()
            if existing:
                message_text = 'Ya existe un complejo con ese slug'
                message_category = 'error'
            else:
                if contact_email and not validate_email(contact_email):
                    message_text = 'Email de contacto no válido'
                    message_category = 'error'
                else:
                    c = Complex(
                        name=name,
                        slug=slug,
                        city=city,
                        address=address or None,
                        contact_phone=contact_phone or None,
                        contact_email=contact_email or None,
                    )
                    db.session.add(c)
                    # Auto-vincular categoría deportes si existe
                    try:
                        deportes = Category.query.filter_by(slug='deportes').first()
                        if deportes and deportes not in c.categories:
                            c.categories.append(deportes)
                    except Exception:
                        current_app.logger.warning('No se pudo vincular categoría deportes al complejo')
                    db.session.commit()
                    message_text = 'Complejo creado correctamente'

    complexes = Complex.query.all()
    # If HTMX, return partial updated; otherwise redirect back
    if request.headers.get('HX-Request'):
        return render_template(
            'admin/partials/_complexes_table.html',
            complexes=complexes,
            message_text=message_text,
            message_category=message_category,
        )
    if message_category == 'error':
        flash(message_text, 'error')
    else:
        flash(message_text, 'success')
    return redirect(url_for('admin.super_admin'))


# ------- Fields (Canchas) management -------
@bp.route('/fields_table')
@login_required
def fields_table():
    """HTMX partial para gestionar canchas (fields) de un complejo.

    Acceso: superadmin o usuarios vinculados al complejo.
    """
    complex_id = request.args.get('complex_id', type=int)
    if not complex_id:
        return jsonify({'success': False, 'message': 'complex_id requerido'}), 400

    # Autorización: superadmin o vínculo con complejo
    if not user_can_manage_complex(getattr(current_user, 'id', None), complex_id):
        return jsonify({'error': 'Unauthorized'}), 403

    complex_obj = Complex.query.get_or_404(complex_id)
    fields = Field.query.filter_by(complex_id=complex_id).order_by(Field.name).all()
    return render_template('admin/partials/_fields_table.html', complex=complex_obj, fields=fields)


@bp.route('/fields/create', methods=['POST'])
@login_required
def fields_create():
    """Crea una cancha para un complejo y devuelve el parcial actualizado.

    Reglas:
    - CSRF: provisto por hidden input en template.
    - Autorización: superadmin o usuarios vinculados al complejo (anti-IDOR).
    - Validación y sanitización de inputs.
    """
    complex_id = request.form.get('complex_id', type=int)
    if not complex_id:
        return jsonify({'success': False, 'message': 'complex_id requerido'}), 400

    # Autorización
    if not user_can_manage_complex(getattr(current_user, 'id', None), complex_id):
        return jsonify({'error': 'Unauthorized'}), 403

    name = clean_text(request.form.get('name', ''), 200)
    sport = clean_text(request.form.get('sport', ''), 100)
    surface = clean_text(request.form.get('surface', ''), 100) or None
    team_size_raw = (request.form.get('team_size') or '').strip()
    is_active = True if (request.form.get('is_active') == 'y') else False

    # Validaciones mínimas
    message_text = ''
    message_category = 'success'
    team_size = None
    if not name or not sport:
        message_text = 'Nombre y deporte son requeridos'
        message_category = 'error'
    else:
        if team_size_raw:
            try:
                ts = int(team_size_raw)
                if ts < 1 or ts > 50:
                    raise ValueError()
                team_size = ts
            except Exception:
                message_text = 'Cantidad de jugadores por equipo inválida'
                message_category = 'error'

    if message_category == 'success':
        f = Field(
            complex_id=complex_id,
            name=name,
            sport=sport,
            team_size=team_size,
            surface=surface,
            is_active=is_active,
        )
        db.session.add(f)
        db.session.commit()
        message_text = 'Cancha creada correctamente'

    complex_obj = Complex.query.get_or_404(complex_id)
    fields = Field.query.filter_by(complex_id=complex_id).order_by(Field.name).all()
    # Responder con el parcial actualizado para el modal HTMX
    return render_template(
        'admin/partials/_fields_table.html',
        complex=complex_obj,
        fields=fields,
        message_text=message_text,
        message_category=message_category,
    )

# ------- Timeslots (Turnos) creation -------
@bp.route('/timeslots/create_form')
@login_required
def timeslots_create_form():
    """Parcial HTMX con el formulario para crear turnos (deportes)."""
    # Restringir a categoría 'deportes' (o superadmin)
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403
    if current_user.is_superadmin:
        available_fields = Field.query.order_by(Field.name).all()
    else:
        user_complexes = db.session.query(UserComplex.complex_id).filter_by(user_id=current_user.id).subquery()
        available_fields = (
            Field.query
            .filter(Field.complex_id.in_(user_complexes))
            .order_by(Field.name)
            .all()
        )
    return render_template('admin/partials/_timeslot_create_form.html', available_fields=available_fields)


# --------- Bulk Timeslots (Deportes) ---------
@bp.route('/timeslots/bulk_form')
@login_required
def timeslots_bulk_form():
    """HTMX partial with bulk-creation form for sports (fields)."""
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403

    if current_user.is_superadmin:
        available_fields = Field.query.order_by(Field.name).all()
    else:
        user_complexes = db.session.query(UserComplex.complex_id).filter_by(user_id=current_user.id).subquery()
        available_fields = (
            Field.query
            .filter(Field.complex_id.in_(user_complexes))
            .order_by(Field.name)
            .all()
        )

    return render_template('admin/partials/_timeslot_bulk_form.html', available_fields=available_fields)


@bp.route('/timeslots/bulk_create', methods=['POST'])
@login_required
def timeslots_bulk_create():
    """Create many timeslots for a field over a date/time window.

    Security:
    - CSRF via template
    - Authorization: deportes admin or superadmin, and ownership of field
    """
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403

    field_id = request.form.get('field_id', type=int)
    start_date_str = (request.form.get('start_date') or '').strip()
    end_date_str = (request.form.get('end_date') or '').strip()
    start_time_str = (request.form.get('start_time') or '').strip()
    end_time_str = (request.form.get('end_time') or '').strip()
    duration_min = request.form.get('duration_min', type=int)
    interval_min = request.form.get('interval_min', type=int)
    price_raw = (request.form.get('price') or '').strip()
    currency = (request.form.get('currency') or 'ARS').strip() or 'ARS'
    weekdays_vals = request.form.getlist('weekdays')

    # Re-fetch available fields for re-rendering the form
    if current_user.is_superadmin:
        available_fields = Field.query.order_by(Field.name).all()
    else:
        user_complexes = db.session.query(UserComplex.complex_id).filter_by(user_id=current_user.id).subquery()
        available_fields = (
            Field.query
            .filter(Field.complex_id.in_(user_complexes))
            .order_by(Field.name)
            .all()
        )

    message_text = ''
    message_category = 'success'

    field = Field.query.get(field_id) if field_id else None
    if not field:
        message_text = 'Cancha inválida'
        message_category = 'error'
    elif not current_user.is_superadmin and not user_can_manage_complex(getattr(current_user, 'id', None), field.complex_id):
        return jsonify({'error': 'Unauthorized'}), 403

    # Parse dates and times
    start_date = end_date = None
    start_time = end_time = None
    if message_category == 'success':
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            message_text = 'Rango de fechas inválido'
            message_category = 'error'

    if message_category == 'success':
        try:
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time = datetime.strptime(end_time_str, '%H:%M').time()
        except Exception:
            message_text = 'Franja horaria inválida'
            message_category = 'error'

    if message_category == 'success':
        if not duration_min or duration_min < 15 or duration_min > 360:
            message_text = 'Duración inválida (15–360)'
            message_category = 'error'

    if message_category == 'success':
        if not interval_min or interval_min < 5 or interval_min > 480:
            interval_min = duration_min

    if message_category == 'success':
        if end_date < start_date:
            message_text = 'La fecha fin debe ser posterior a inicio'
            message_category = 'error'

    # Limit guard rails (avoid massive explosions)
    if message_category == 'success':
        max_days = 120
        days = (end_date - start_date).days + 1
        if days > max_days:
            message_text = f'Rango demasiado grande (máx {max_days} días)'
            message_category = 'error'

    # Weekdays
    if message_category == 'success':
        try:
            weekdays = [int(w) for w in weekdays_vals]
        except Exception:
            weekdays = []
        if not weekdays:
            message_text = 'Seleccioná al menos un día de la semana'
            message_category = 'error'

    # Price
    price = None
    if message_category == 'success' and price_raw:
        try:
            price = float(price_raw.replace(',', '.'))
            if price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio inválido'
            message_category = 'error'

    created = skipped = 0
    if message_category == 'success':
        created, skipped = generate_timeslots_for_field(
            field=field,
            start_date=start_date,
            end_date=end_date,
            start_time=start_time,
            end_time=end_time,
            duration_min=duration_min,
            interval_min=interval_min,
            weekdays=weekdays,
            price=price,
            currency=currency,
            status=TimeslotStatus.AVAILABLE,
        )
        message_text = f'Turnos creados: {created}. Omitidos por solape: {skipped}.'

    return render_template(
        'admin/partials/_timeslot_bulk_form.html',
        available_fields=available_fields,
        message_text=message_text,
        message_category=message_category,
    )

@bp.route('/timeslots/create', methods=['POST'])
@login_required
def timeslots_create():
    """Crea un turno para una cancha seleccionada.

    Seguridad:
    - CSRF requerido (via hidden input en template)
    - Autorización: superadmin o usuario vinculado al complejo (anti-IDOR)
    - Validaciones: fecha/hora futuras, duración válida, no solapar con turnos existentes
    """
    # Restringir a categoría 'deportes' (o superadmin)
    if not (current_user.is_superadmin or (getattr(current_user, 'category', None) and getattr(current_user.category, 'slug', None) == 'deportes')):
        return jsonify({'error': 'Unauthorized'}), 403
    field_id = request.form.get('field_id', type=int)
    start_str = (request.form.get('start') or '').strip()
    duration_min = request.form.get('duration_min', type=int)
    price_raw = (request.form.get('price') or '').strip()

    # Recolectar campos disponibles para re-render del formulario
    if current_user.is_superadmin:
        available_fields = Field.query.order_by(Field.name).all()
    else:
        user_complexes = db.session.query(UserComplex.complex_id).filter_by(user_id=current_user.id).subquery()
        available_fields = (
            Field.query
            .filter(Field.complex_id.in_(user_complexes))
            .order_by(Field.name)
            .all()
        )

    message_text = ''
    message_category = 'success'

    # Validaciones básicas
    field = Field.query.get(field_id) if field_id else None
    if not field:
        message_text = 'Cancha inválida'
        message_category = 'error'
    elif not user_can_manage_complex(getattr(current_user, 'id', None), field.complex_id):
        return jsonify({'error': 'Unauthorized'}), 403

    # Parseo fecha/hora local (datetime-local => YYYY-MM-DDTHH:MM)
    start_dt = None
    if message_category == 'success':
        try:
            # Interpretar como hora local y almacenar como UTC aware
            start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        except Exception:
            message_text = 'Fecha y hora de inicio inválidas'
            message_category = 'error'

    # Duración mínima
    if message_category == 'success':
        if not duration_min or duration_min < 15 or duration_min > 360:
            message_text = 'Duración inválida (15–360 minutos)'
            message_category = 'error'

    # No crear en el pasado
    if message_category == 'success':
        now = datetime.now(timezone.utc)
        if start_dt <= now:
            message_text = 'La hora de inicio debe ser futura'
            message_category = 'error'

    # Calcular fin
    end_dt = None
    if message_category == 'success':
        end_dt = start_dt + timedelta(minutes=duration_min)

    # Precio opcional
    price = None
    if message_category == 'success' and price_raw:
        try:
            # Permitir coma o punto como separador
            norm = price_raw.replace(',', '.')
            price = float(norm)
            if price < 0:
                raise ValueError()
        except Exception:
            message_text = 'Precio inválido'
            message_category = 'error'

    # Evitar solapamiento en la misma cancha
    if message_category == 'success':
        overlap = (
            Timeslot.query
            .filter(
                Timeslot.field_id == field.id,
                Timeslot.start < end_dt,
                Timeslot.end > start_dt,
            )
            .first()
        )
        if overlap:
            message_text = 'Existe un turno que se solapa en esa franja'
            message_category = 'error'

    # Crear turno
    if message_category == 'success':
        t = Timeslot(
            field_id=field.id,
            start=start_dt,
            end=end_dt,
            price=price,
            currency='ARS',
            status=TimeslotStatus.AVAILABLE,
        )
        db.session.add(t)
        db.session.commit()
        message_text = 'Turno creado correctamente'

    # Re-render del formulario (parcial HTMX)
    return render_template(
        'admin/partials/_timeslot_create_form.html',
        available_fields=available_fields,
        message_text=message_text,
        message_category=message_category,
    )

@bp.route('/users_table')
@login_required
@superadmin_required
def users_table():
    """HTMX partial for users management"""
    users = AppUser.query.all()
    categories = Category.query.order_by(Category.title).all()
    # Para selects dependientes según categoría seleccionada por usuario via HTMX
    return render_template('admin/partials/_users_table.html', users=users, categories=categories)

@bp.route('/users/create', methods=['POST'])
@login_required
@superadmin_required
def users_create():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    is_super = request.form.get('is_superadmin') == 'on'
    category_slug = request.form.get('category', '').strip()
    entity_id = request.form.get('entity_id', type=int)

    if not email or not password:
        if request.headers.get('HX-Request'):
            users = AppUser.query.all()
            categories = Category.query.order_by(Category.title).all()
            return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                                   message_text='Email y contraseña son requeridos', message_category='error')
        flash('Email y contraseña son requeridos', 'error')
        return redirect(url_for('admin.users_table'))

    existing = AppUser.query.filter_by(email=email).first()
    if existing:
        if request.headers.get('HX-Request'):
            users = AppUser.query.all()
            categories = Category.query.order_by(Category.title).all()
            return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                                   message_text='El email ya existe', message_category='error')
        flash('El email ya existe', 'error')
        return redirect(url_for('admin.users_table'))

    user = AppUser(email=email, is_superadmin=bool(is_super))
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    if not is_super:
        if not category_slug or not entity_id:
            db.session.rollback()
            if request.headers.get('HX-Request'):
                users = AppUser.query.all()
                categories = Category.query.order_by(Category.title).all()
                return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                                       message_text='Selecciona categoría y entidad para usuarios Admin.', message_category='error')
            flash('Selecciona categoría y entidad para usuarios Admin.', 'error')
            return redirect(url_for('admin.users_table'))
        cat = Category.query.filter_by(slug=category_slug).first()
        if not cat:
            db.session.rollback()
            if request.headers.get('HX-Request'):
                users = AppUser.query.all()
                categories = Category.query.order_by(Category.title).all()
                return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                                       message_text='Categoría inválida', message_category='error')
            flash('Categoría inválida', 'error')
            return redirect(url_for('admin.users_table'))
        user.category_id = cat.id
        if cat.slug == 'deportes':
            db.session.add(UserComplex(user_id=user.id, complex_id=entity_id))
        elif cat.slug == 'estetica':
            db.session.execute(user_beauty_centers.insert().values(user_id=user.id, beauty_center_id=entity_id))
        else:
            db.session.execute(user_professionals.insert().values(user_id=user.id, professional_id=entity_id))

    db.session.commit()
    flash('Usuario creado correctamente', 'success')

    # Si viene de HTMX, devolver el parcial actualizado para mantener al usuario en el panel
    if request.headers.get('HX-Request'):
        users = AppUser.query.all()
        categories = Category.query.order_by(Category.title).all()
        return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                               message_text='Usuario creado correctamente', message_category='success')

    # Fallback navegación completa
    return redirect(url_for('admin.super_admin'))


@bp.get('/users/edit')
@login_required
@superadmin_required
def users_edit():
    user_id = request.args.get('user_id', type=int)
    user = AppUser.query.get_or_404(user_id)
    categories = Category.query.order_by(Category.title).all()
    # Preload items for current category
    items = []
    kind = None
    if user.category:
        if user.category.slug == 'deportes':
            items = Complex.query.order_by(Complex.name).all()
            kind = 'complex'
        elif user.category.slug == 'estetica':
            items = BeautyCenter.query.order_by(BeautyCenter.name).all()
            kind = 'beauty'
        else:
            items = Professional.query.order_by(Professional.name).all()
            kind = 'professional'
    return render_template('admin/partials/_user_edit_form.html', user=user, categories=categories, items=items, kind=kind)


@bp.post('/users/update')
@login_required
@superadmin_required
def users_update():
    user_id = request.form.get('user_id', type=int)
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    is_super = request.form.get('is_superadmin') == 'on'
    category_slug = request.form.get('category', '').strip()
    entity_id = request.form.get('entity_id', type=int)

    user = AppUser.query.get_or_404(user_id)
    if email:
        exists = AppUser.query.filter(AppUser.email==email, AppUser.id!=user.id).first()
        if exists:
            flash('El email ya existe', 'error')
            return redirect(url_for('admin.users_table'))
        user.email = email
    if password:
        user.set_password(password)
    user.is_superadmin = bool(is_super)

    if not is_super:
        if not category_slug or not entity_id:
            flash('Selecciona categoría y entidad para usuarios Admin.', 'error')
            return redirect(url_for('admin.users_table'))
        cat = Category.query.filter_by(slug=category_slug).first()
        if not cat:
            flash('Categoría inválida', 'error')
            return redirect(url_for('admin.users_table'))
        user.category_id = cat.id
        # reset and link according to category
        if cat.slug == 'deportes':
            UserComplex.query.filter_by(user_id=user.id).delete()
            db.session.add(UserComplex(user_id=user.id, complex_id=entity_id))
        elif cat.slug == 'estetica':
            db.session.execute(user_beauty_centers.delete().where(user_beauty_centers.c.user_id==user.id))
            db.session.execute(user_beauty_centers.insert().values(user_id=user.id, beauty_center_id=entity_id))
        else:
            db.session.execute(user_professionals.delete().where(user_professionals.c.user_id==user.id))
            db.session.execute(user_professionals.insert().values(user_id=user.id, professional_id=entity_id))
    else:
        user.category_id = None

    db.session.commit()
    users = AppUser.query.all()
    categories = Category.query.order_by(Category.title).all()
    return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                           message_text='Usuario actualizado', message_category='success')


@bp.route('/users/set_category', methods=['POST'])
@login_required
@superadmin_required
def users_set_category():
    user_id = request.form.get('user_id', type=int)
    category_slug = request.form.get('category')
    user = AppUser.query.get_or_404(user_id)
    category = Category.query.filter_by(slug=category_slug).first()
    if not category:
        return jsonify({'success': False, 'message': 'Categoría inválida'}), 400
    user.category_id = category.id
    db.session.commit()

    if request.headers.get('HX-Request'):
        users = AppUser.query.all()
        categories = Category.query.order_by(Category.title).all()
        return render_template('admin/partials/_users_table.html', users=users, categories=categories)
    return redirect(url_for('admin.super_admin'))


@bp.route('/users/link', methods=['POST'])
@login_required
@superadmin_required
def users_link():
    user_id = request.form.get('user_id', type=int)
    kind = request.form.get('kind')
    entity_id = request.form.get('entity_id', type=int)

    user = AppUser.query.get_or_404(user_id)
    if kind == 'complex':
        if not db.session.query(UserComplex).filter_by(user_id=user.id, complex_id=entity_id).first():
            db.session.add(UserComplex(user_id=user.id, complex_id=entity_id))
    elif kind == 'professional':
        db.session.execute(user_professionals.insert().prefix_with('OR IGNORE') if db.session.bind.dialect.name=='sqlite' else user_professionals.insert().values(user_id=user.id, professional_id=entity_id).prefix_with('ON CONFLICT DO NOTHING'))
        # Fallback simple: evitar duplicados manualmente
        exists = db.session.execute(db.select(user_professionals).where(user_professionals.c.user_id==user.id, user_professionals.c.professional_id==entity_id)).first()
        if not exists:
            db.session.execute(user_professionals.insert().values(user_id=user.id, professional_id=entity_id))
    elif kind == 'beauty':
        exists = db.session.execute(db.select(user_beauty_centers).where(user_beauty_centers.c.user_id==user.id, user_beauty_centers.c.beauty_center_id==entity_id)).first()
        if not exists:
            db.session.execute(user_beauty_centers.insert().values(user_id=user.id, beauty_center_id=entity_id))
    else:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    db.session.commit()

    if request.headers.get('HX-Request'):
        users = AppUser.query.all()
        categories = Category.query.order_by(Category.title).all()
        return render_template('admin/partials/_users_table.html', users=users, categories=categories)
    return redirect(url_for('admin.super_admin'))


@bp.route('/users/unlink', methods=['POST'])
@login_required
@superadmin_required
def users_unlink():
    user_id = request.form.get('user_id', type=int)
    kind = request.form.get('kind')
    entity_id = request.form.get('entity_id', type=int)

    user = AppUser.query.get_or_404(user_id)
    if kind == 'complex':
        UserComplex.query.filter_by(user_id=user.id, complex_id=entity_id).delete()
    elif kind == 'professional':
        db.session.execute(user_professionals.delete().where(user_professionals.c.user_id==user.id, user_professionals.c.professional_id==entity_id))
    elif kind == 'beauty':
        db.session.execute(user_beauty_centers.delete().where(user_beauty_centers.c.user_id==user.id, user_beauty_centers.c.beauty_center_id==entity_id))
    else:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    db.session.commit()
    if request.headers.get('HX-Request'):
        users = AppUser.query.all()
        categories = Category.query.order_by(Category.title).all()
        return render_template('admin/partials/_users_table.html', users=users, categories=categories,
                               message_text='Vínculo eliminado', message_category='success')
    return redirect(url_for('admin.super_admin'))


@bp.route('/users/entities_options')
@login_required
@superadmin_required
def users_entities_options():
    user_id = request.args.get('user_id', type=int)
    user = AppUser.query.get_or_404(user_id)
    if not user.category:
        return jsonify({'success': False, 'message': 'Usuario sin categoría'}), 400
    if user.category.slug == 'deportes':
        items = Complex.query.order_by(Complex.name).all()
        return render_template('admin/partials/_user_entities_options.html', kind='complex', items=items)
    elif user.category.slug == 'estetica':
        items = BeautyCenter.query.order_by(BeautyCenter.name).all()
        return render_template('admin/partials/_user_entities_options.html', kind='beauty', items=items)
    else:
        items = Professional.query.order_by(Professional.name).all()
        return render_template('admin/partials/_user_entities_options.html', kind='professional', items=items)

@bp.route('/professionals_table')
@login_required
@superadmin_required
def professionals_table():
    pros = Professional.query.order_by(Professional.name).all()
    return render_template('admin/partials/_professionals_table.html', professionals=pros)

@bp.route('/beauty_centers_table')
@login_required
@superadmin_required
def beauty_centers_table():
    centers = BeautyCenter.query.order_by(BeautyCenter.name).all()
    return render_template('admin/partials/_beauty_centers_table.html', centers=centers)

@bp.route('/users/entity_options_by_category')
@login_required
@superadmin_required
def users_entity_options_by_category():
    slug = request.args.get('category', '').strip()
    if slug == 'deportes':
        items = Complex.query.order_by(Complex.name).all()
        return render_template('admin/partials/_user_entities_options.html', kind='complex', items=items)
    elif slug == 'estetica':
        items = BeautyCenter.query.order_by(BeautyCenter.name).all()
        return render_template('admin/partials/_user_entities_options.html', kind='beauty', items=items)
    elif slug == 'profesionales':
        items = Professional.query.order_by(Professional.name).all()
        return render_template('admin/partials/_user_entities_options.html', kind='professional', items=items)
    else:
        return render_template('admin/partials/_user_entities_options.html', kind='professional', items=[])


# HTMX endpoint to create catalog entities with partial refresh
@bp.route('/catalog/create_hx/<kind>', methods=['POST'])
@login_required
@superadmin_required
def catalog_create_hx(kind):
    # Map model and category by kind
    kind = (kind or '').strip().lower()
    Model = None
    category_slug = None
    field_map = {}
    if kind == 'professional':
        Model = Professional
        category_slug = 'profesionales'
        field_map = {
            'name': 'name',
            'slug': 'slug',
            'city': 'city',
            'address': 'address',
            'phone': 'phone',
            'website': 'website',
            'specialties': 'specialties',
        }
    elif kind == 'beauty':
        Model = BeautyCenter
        category_slug = 'estetica'
        field_map = {
            'name': 'name',
            'slug': 'slug',
            'city': 'city',
            'address': 'address',
            'phone': 'phone',
            'website': 'website',
            'services': 'services',
        }
    elif kind == 'sports':
        Model = SportsComplex
        category_slug = 'deportes'
        field_map = {
            'name': 'name',
            'slug': 'slug',
            'city': 'city',
            'address': 'address',
            'phone': 'phone',
            'website': 'website',
            'sports': 'sports',
        }
    else:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    # Extract and sanitize
    raw = {k: (request.form.get(k) or '').strip() for k in field_map.keys()}
    name = clean_text(raw.get('name', ''), 200)
    slug = clean_text((raw.get('slug') or '').lower(), 180)
    city = clean_text(raw.get('city', ''), 120) if raw.get('city') else None
    address = clean_text(raw.get('address', ''), 200) if raw.get('address') else None
    phone = clean_text(raw.get('phone', ''), 60) if raw.get('phone') else None
    website = clean_text(raw.get('website', ''), 200) if raw.get('website') else None
    extra_key = None
    if kind == 'professional':
        extra_key = 'specialties'
    elif kind == 'beauty':
        extra_key = 'services'
    elif kind == 'sports':
        extra_key = 'sports'
    extra_val = clean_text(raw.get(extra_key, ''), 240) if extra_key and raw.get(extra_key) else None

    message_text = None
    message_category = None

    import re
    if not name or not slug:
        message_text = 'Nombre y slug son requeridos'
        message_category = 'error'
    elif not re.match(r'^[a-z0-9\-]+$', slug):
        message_text = 'El slug solo puede contener a-z, 0-9 y guiones (-)'
        message_category = 'error'
    else:
        exists = Model.query.filter_by(slug=slug).first()
        if exists:
            message_text = 'Ya existe un elemento con ese slug'
            message_category = 'error'
        else:
            category = Category.query.filter_by(slug=category_slug).first()
            if not category:
                message_text = 'Categoría no encontrada'
                message_category = 'error'
            else:
                data = dict(
                    name=name,
                    slug=slug,
                    city=city,
                    address=address,
                    phone=phone,
                    website=website,
                    category_id=category.id,
                )
                if extra_key:
                    data[extra_key] = extra_val
                obj = Model(**data)
                db.session.add(obj)
                db.session.commit()
                message_text = 'Creado correctamente'
                message_category = 'success'

    # Return the forms partial updated for HTMX target
    return render_template(
        'admin/partials/_catalog_forms.html',
        prof_form=ProfessionalForm(),
        beauty_form=BeautyCenterForm(),
        sports_form=SportsComplexForm(),
        message_text=message_text,
        message_category=message_category,
    )
