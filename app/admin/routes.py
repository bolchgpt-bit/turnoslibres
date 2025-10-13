from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.admin import bp
from app.admin.forms import LoginForm, RegistrationForm, ProfessionalForm, BeautyCenterForm, SportsComplexForm
from app.models import AppUser, Complex, Category, Service, Field, Timeslot, TimeslotStatus, UserComplex, user_professionals, user_beauty_centers
from app.models_catalog import Professional, BeautyCenter, SportsComplex
from app import db
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

@bp.route('/super')
@login_required
@superadmin_required
def super_admin():
    """Vista exclusiva para superadministradores."""
    if not current_user.is_superadmin:
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('admin.panel'))
    
    return render_template('admin/super.html')

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
    limit = min(int(request.args.get('limit', 20)), 50)
    
    # Build base query - only show turnos from complexes the user can manage
    if current_user.is_superadmin:
        query = Timeslot.query
    else:
        # Get user's complexes
        user_complexes = db.session.query(UserComplex.complex_id).filter_by(user_id=current_user.id).subquery()
        query = Timeslot.query.join(Field).filter(Field.complex_id.in_(user_complexes))
    
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
            pass
    
    # Category filter
    if category and validate_category(category):
        if category == 'deportes':
            query = query.join(Field).join(Complex).join(Complex.categories).filter(Category.slug == category)
        else:
            query = query.join(Service).join(Category).filter(Category.slug == category)
    
    # Status filter
    if status and validate_status(status):
        query = query.filter(Timeslot.status == TimeslotStatus(status))
    
    # Complex filter
    if complex_slug:
        complex_slug = clean_text(complex_slug, 200)
        query = query.join(Field).join(Complex).filter(Complex.slug.ilike(f'%{complex_slug}%'))
    
    # Sport/Service filter
    if sport_service:
        sport_service = clean_text(sport_service, 100)
        if category == 'deportes':
            query = query.join(Field).filter(Field.sport.ilike(f'%{sport_service}%'))
        else:
            query = query.join(Service).filter(Service.name.ilike(f'%{sport_service}%'))
    
    # Exclude past timeslots (only show those starting after now)
    now = datetime.now(timezone.utc)
    query = query.filter(Timeslot.start > now)

    # Order and paginate
    query = query.order_by(Timeslot.start)
    total = query.count()
    offset = (page - 1) * limit
    timeslots = query.offset(offset).limit(limit).all()
    
    # Calculate pagination info
    has_next = total > (page * limit)
    has_prev = page > 1
    
    return render_template('admin/partials/_admin_turnos_table.html', 
                         timeslots=timeslots,
                         page=page,
                         has_next=has_next,
                         has_prev=has_prev,
                         total=total)

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
