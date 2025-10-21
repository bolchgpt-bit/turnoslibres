from flask import render_template, request, jsonify, current_app
from app.ui import bp
from app.models import Timeslot, Field, Service, Complex, Category, Subscription, TimeslotStatus, SubscriptionStatus
from app.utils import validate_category, validate_span, validate_status, validate_date_format, validate_email, clean_text
from app.services.notification_service import NotificationService
from app import db, limiter
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_

@bp.route('/turnos_table')
def turnos_table():
    """HTMX partial for day view turnos table"""
    # Get and validate parameters
    date_str = request.args.get('date', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    complex_slug = request.args.get('complex_slug', '')
    sport_service = request.args.get('sport_service', '')
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), 50)  # Max 50 items per page
    
    # Build query
    query = Timeslot.query
    
    # Date filter
    if date_str and validate_date_format(date_str):
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(
                and_(
                    Timeslot.start >= target_date,
                    Timeslot.start < target_date + timedelta(days=1)
                )
            )
        except ValueError:
            current_app.logger.debug("Invalid date format for 'date' in turnos_table: %s", date_str)
    
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
        if category == 'deportes':
            query = query.join(Field).join(Complex).filter(Complex.slug == complex_slug)
        else:
            # For services, we need to join through the complex-category relationship
            query = query.join(Service).join(Category).join(Category.complexes).filter(Complex.slug == complex_slug)
    
    # Sport/Service filter
    if sport_service:
        sport_service = clean_text(sport_service, 100)
        if category == 'deportes':
            query = query.join(Field).filter(Field.sport.ilike(f'%{sport_service}%'))
        else:
            query = query.join(Service).filter(Service.name.ilike(f'%{sport_service}%'))
    
    # Exclude past timeslots (only show starting after current datetime)
    now = datetime.now(timezone.utc)
    query = query.filter(Timeslot.start > now)

    # Order and paginate
    query = query.order_by(Timeslot.start)
    
    # Get total count for pagination
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    timeslots = query.offset(offset).limit(limit).all()
    
    # Calculate pagination info
    has_next = total > (page * limit)
    has_prev = page > 1
    
    return render_template('partials/_turnos_table.html', 
                         timeslots=timeslots,
                         page=page,
                         has_next=has_next,
                         has_prev=has_prev,
                         total=total)

@bp.route('/turnos_table_grouped')
def turnos_table_grouped():
    """HTMX partial for week view turnos table grouped by day"""
    # Get and validate parameters
    date_str = request.args.get('date', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    complex_slug = request.args.get('complex_slug', '')
    sport_service = request.args.get('sport_service', '')
    
    # Calculate week range
    if date_str and validate_date_format(date_str):
        try:
            start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            current_app.logger.debug("Invalid date format for 'date' in turnos_table_grouped: %s", date_str)
            start_date = datetime.now().date()
    else:
        start_date = datetime.now().date()
    
    # Get start of week (Monday)
    days_since_monday = start_date.weekday()
    week_start = start_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=7)
    
    # Build query (similar to turnos_table but for week range)
    query = Timeslot.query.filter(
        and_(
            Timeslot.start >= week_start,
            Timeslot.start < week_end
        )
    )
    # Exclude past timeslots relative to current datetime
    now = datetime.now(timezone.utc)
    query = query.filter(Timeslot.start > now)
    
    # Apply same filters as turnos_table
    if category and validate_category(category):
        if category == 'deportes':
            query = query.join(Field).join(Complex).join(Complex.categories).filter(Category.slug == category)
        else:
            query = query.join(Service).join(Category).filter(Category.slug == category)
    
    if status and validate_status(status):
        query = query.filter(Timeslot.status == TimeslotStatus(status))
    
    if complex_slug:
        complex_slug = clean_text(complex_slug, 200)
        if category == 'deportes':
            query = query.join(Field).join(Complex).filter(Complex.slug == complex_slug)
        else:
            query = query.join(Service).join(Category).join(Category.complexes).filter(Complex.slug == complex_slug)
    
    if sport_service:
        sport_service = clean_text(sport_service, 100)
        if category == 'deportes':
            query = query.join(Field).filter(Field.sport.ilike(f'%{sport_service}%'))
        else:
            query = query.join(Service).filter(Service.name.ilike(f'%{sport_service}%'))
    
    # Get timeslots and group by day
    timeslots = query.order_by(Timeslot.start).all()

    # Group by day and compute simple counters per status for headers
    grouped_timeslots = {}
    day_counts = {}
    for timeslot in timeslots:
        day = timeslot.start.date()
        grouped_timeslots.setdefault(day, []).append(timeslot)
        if day not in day_counts:
            day_counts[day] = {"available": 0, "holding": 0, "reserved": 0, "blocked": 0}
        val = getattr(getattr(timeslot, 'status', None), 'value', None) or str(timeslot.status)
        if val in day_counts[day]:
            day_counts[day][val] += 1

    return render_template(
        'partials/_turnos_table_grouped.html',
        grouped_timeslots=grouped_timeslots,
        day_counts=day_counts,
        week_start=week_start,
        week_end=week_end,
    )

@bp.route('/subscribe', methods=['POST'])
@limiter.limit("5 per minute")
def subscribe():
    """HTMX endpoint to create waitlist subscription"""
    email = request.form.get('email', '').strip().lower()
    timeslot_id = request.form.get('timeslot_id')
    
    # Validate email
    if not validate_email(email):
        return render_template('partials/_subscription_result.html', 
                             success=False, 
                             message='Email no válido.')
    
    # Validate timeslot
    if not timeslot_id:
        return render_template('partials/_subscription_result.html', 
                             success=False, 
                             message='Turno no especificado.')
    
    try:
        timeslot_id = int(timeslot_id)
        timeslot = Timeslot.query.get(timeslot_id)
        if not timeslot:
            return render_template('partials/_subscription_result.html', 
                                 success=False, 
                                 message='Turno no encontrado.')
        
        # Check if timeslot is available (shouldn't subscribe to available slots)
        if timeslot.status == TimeslotStatus.AVAILABLE:
            return render_template('partials/_subscription_result.html', 
                                 success=False, 
                                 message='Este turno está disponible. Puedes reservarlo directamente.')
        
        success, message = NotificationService.create_timeslot_subscription(email, timeslot_id)
        
        return render_template('partials/_subscription_result.html', 
                             success=success, 
                             message=message)
        
    except (ValueError, TypeError):
        return render_template('partials/_subscription_result.html', 
                             success=False, 
                             message='Datos inválidos.')

@bp.route('/subscribe_criteria', methods=['POST'])
@limiter.limit("3 per minute")
def subscribe_criteria():
    """HTMX endpoint to create criteria-based waitlist subscription"""
    email = request.form.get('email', '').strip().lower()
    field_id = request.form.get('field_id')
    service_id = request.form.get('service_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    start_time = request.form.get('start_time', '00:00')
    end_time = request.form.get('end_time', '23:59')
    
    # Validate email
    if not validate_email(email):
        return render_template('partials/_subscription_result.html', 
                             success=False, 
                             message='Email no válido.')
    
    # Validate dates
    if not start_date or not end_date:
        return render_template('partials/_subscription_result.html', 
                             success=False, 
                             message='Fechas requeridas.')
    
    try:
        # Parse dates and times
        start_datetime = datetime.strptime(f"{start_date} {start_time}", '%Y-%m-%d %H:%M')
        end_datetime = datetime.strptime(f"{end_date} {end_time}", '%Y-%m-%d %H:%M')
        
        if start_datetime >= end_datetime:
            return render_template('partials/_subscription_result.html', 
                                 success=False, 
                                 message='La fecha de inicio debe ser anterior a la fecha de fin.')
        
        # Validate field or service
        field_id = int(field_id) if field_id else None
        service_id = int(service_id) if service_id else None
        
        if not field_id and not service_id:
            return render_template('partials/_subscription_result.html', 
                                 success=False, 
                                 message='Debe especificar un campo o servicio.')
        
        # Create criteria subscription
        success, message = NotificationService.create_criteria_subscription(
            email=email,
            field_id=field_id,
            service_id=service_id,
            start_window=start_datetime,
            end_window=end_datetime
        )
        
        return render_template('partials/_subscription_result.html', 
                             success=success, 
                             message=message)
        
    except (ValueError, TypeError) as e:
        return render_template('partials/_subscription_result.html', 
                             success=False, 
                             message='Datos inválidos.')
