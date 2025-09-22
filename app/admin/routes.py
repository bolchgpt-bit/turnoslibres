from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.admin import bp
from app.admin.forms import LoginForm, RegistrationForm
from app.models import AppUser, Complex, Category, Service, Field, Timeslot, TimeslotStatus, UserComplex
from app import db
from app.utils import user_can_manage_complex, validate_date_format, validate_span, validate_category, validate_status, clean_text
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

@bp.route('/login', methods=['GET', 'POST'])
def login():
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
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('main.index'))

@bp.route('/panel')
@login_required
def panel():
    return render_template('admin/panel.html')

@bp.route('/super')
@login_required
def super_admin():
    if not current_user.is_superadmin:
        flash('No tienes permisos para acceder a esta página.', 'error')
        return redirect(url_for('admin.panel'))
    
    return render_template('admin/super.html')

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
def categories_table():
    """HTMX partial for categories management"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    categories = Category.query.all()
    return render_template('admin/partials/_categories_table.html', categories=categories)

@bp.route('/services_table')
@login_required
def services_table():
    """HTMX partial for services management"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    services = Service.query.join(Category).all()
    return render_template('admin/partials/_services_table.html', services=services)

@bp.route('/complexes_table')
@login_required
def complexes_table():
    """HTMX partial for complexes management"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    complexes = Complex.query.all()
    return render_template('admin/partials/_complexes_table.html', complexes=complexes)

@bp.route('/users_table')
@login_required
def users_table():
    """HTMX partial for users management"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = AppUser.query.all()
    return render_template('admin/partials/_users_table.html', users=users)
