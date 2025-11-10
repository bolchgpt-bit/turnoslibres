from flask import render_template, request, jsonify, current_app, abort
from app.ui import bp
from app.models import Timeslot, Field, Service, Complex, Category, Subscription, TimeslotStatus, SubscriptionStatus
from app.models_catalog import BeautyCenter, beauty_center_services
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
    beauty_slug = request.args.get('beauty_slug', '')
    sport_service = request.args.get('sport_service', '')
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), 50)  # Max 50 items per page
    
    # Enforce complex public visibility if filtering by complex
    if complex_slug:
        cs = clean_text(complex_slug, 200)
        from app.models import Complex as _Complex
        c = _Complex.query.filter_by(slug=cs).first()
        if c is not None and not getattr(c, 'show_public_booking', True):
            return (
                jsonify({'error': 'Forbidden'}) if request.headers.get('HX-Request') else abort(403)
            )

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
            # Soft-hide fields with public booking disabled
            query = query.filter(Field.show_public_booking.is_(True))
        else:
            query = query.join(Service).join(Category).filter(Category.slug == category)
    
    # Status filter
    if status and validate_status(status):
        query = query.filter(Timeslot.status == TimeslotStatus(status))
    
    # Complex / Center filter
    if complex_slug:
        complex_slug = clean_text(complex_slug, 200)
        if category == 'deportes':
            query = query.filter(Complex.slug == complex_slug)
        else:
            # For services, we need to join through the complex-category relationship
            query = query.join(Service).join(Category).join(Category.complexes).filter(Complex.slug == complex_slug)
    elif beauty_slug and category == 'estetica':
        beauty_slug = clean_text(beauty_slug, 200)
        center = BeautyCenter.query.filter_by(slug=beauty_slug).first()
        if center:
            # Prefer FK
            query = query.join(Service)
            query = query.outerjoin(beauty_center_services, beauty_center_services.c.service_id == Service.id)
            query = query.filter(or_(
                Timeslot.beauty_center_id == center.id,
                and_(Timeslot.beauty_center_id.is_(None), beauty_center_services.c.beauty_center_id == center.id)
            ))
        else:
            # Fallback by slug on mapping only
            query = query.join(Service).join(beauty_center_services, beauty_center_services.c.service_id == Service.id)
            query = query.join(BeautyCenter, beauty_center_services.c.beauty_center_id == BeautyCenter.id)
            query = query.filter(BeautyCenter.slug == beauty_slug)
    
    # Sport/Service filter
    if sport_service:
        sport_service = clean_text(sport_service, 100)
        if category == 'deportes':
            query = query.filter(Field.sport.ilike(f'%{sport_service}%'))
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
        current_app.logger.warning(f"Lazy expire holds failed: {_e}")
    
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
    beauty_slug = request.args.get('beauty_slug', '')
    sport_service = request.args.get('sport_service', '')
    
    # Enforce complex public visibility if filtering by complex
    if complex_slug:
        cs = clean_text(complex_slug, 200)
        from app.models import Complex as _Complex
        c = _Complex.query.filter_by(slug=cs).first()
        if c is not None and not getattr(c, 'show_public_booking', True):
            return (
                jsonify({'error': 'Forbidden'}) if request.headers.get('HX-Request') else abort(403)
            )

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
            query = query.filter(Field.show_public_booking.is_(True))
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
    elif beauty_slug and category == 'estetica':
        beauty_slug = clean_text(beauty_slug, 200)
        center = BeautyCenter.query.filter_by(slug=beauty_slug).first()
        if center:
            query = query.join(Service)
            query = query.outerjoin(beauty_center_services, beauty_center_services.c.service_id == Service.id)
            query = query.filter(or_(
                Timeslot.beauty_center_id == center.id,
                and_(Timeslot.beauty_center_id.is_(None), beauty_center_services.c.beauty_center_id == center.id)
            ))
        else:
            query = query.join(Service).join(beauty_center_services, beauty_center_services.c.service_id == Service.id)
            query = query.join(BeautyCenter, beauty_center_services.c.beauty_center_id == BeautyCenter.id)
            query = query.filter(BeautyCenter.slug == beauty_slug)
    
    if sport_service:
        sport_service = clean_text(sport_service, 100)
        if category == 'deportes':
            query = query.join(Field).filter(Field.sport.ilike(f'%{sport_service}%'))
        else:
            query = query.join(Service).filter(Service.name.ilike(f'%{sport_service}%'))
    
    # Get timeslots
    timeslots = query.order_by(Timeslot.start).all()

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
        current_app.logger.warning(f"Lazy expire holds failed: {_e}")

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


@bp.get('/beauty/availability')
def beauty_availability():
    """HTMX partial: available start times for a BeautyCenter given selected service(s) and date.

    MVP: soporta un único servicio. Combos se agregarán en una iteración posterior.
    - Usa Timeslot como fuente de verdad (status AVAILABLE) para el centro.
    - Granularidad derivada de los slots existentes (ideal 15 minutos cuando esté configurado).
    """
    beauty_slug = clean_text(request.args.get('beauty_slug', ''), 200)
    service_ids_raw = request.args.getlist('service_id') or []
    date_str = request.args.get('date', '')

    center = BeautyCenter.query.filter_by(slug=beauty_slug).first()
    if not center:
        return render_template('partials/_availability.html',
                               center=None,
                               available_starts=[],
                               services=[],
                               message='Centro no encontrado.')
    # Enforce public visibility toggle
    if not getattr(center, 'show_public_booking', True):
        abort(403)

    # Validar fecha
    if not (date_str and validate_date_format(date_str)):
        return render_template('partials/_availability.html',
                               center=center,
                               available_starts=[],
                               services=[],
                               message='Fecha inválida o no especificada.')

    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return render_template('partials/_availability.html',
                               center=center,
                               available_starts=[],
                               services=[],
                               message='Fecha inválida.')

    # Servicios seleccionados (soporta múltiples; suma duraciones)
    try:
        service_ids = [int(sid) for sid in service_ids_raw if sid]
    except ValueError:
        service_ids = []

    services = []
    if service_ids:
        services = Service.query.filter(Service.id.in_(service_ids)).all()
    if not services:
        return render_template('partials/_availability.html',
                               center=center,
                               available_starts=[],
                               services=[],
                               message='Seleccioná al menos un servicio.')

    # Duración total requerida
    total_duration_min = 0
    for s in services:
        total_duration_min += int(getattr(s, 'duration_min', 0) or 0)
    if total_duration_min <= 0:
        return render_template('partials/_availability.html',
                               center=center,
                               available_starts=[],
                               services=services,
                               message='Los servicios seleccionados no tienen duración configurada.')

    # Ventana del día
    day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    # Buscar profesionales del centro que puedan cubrir TODOS los servicios
    # Nota: el admin define qué staff puede hacer cada servicio (professional_services)
    pros = list(getattr(center, 'professionals', []) or [])
    if pros:
        service_id_set = set(service_ids)
        capable_pros = []
        for p in pros:
            try:
                p_services = {s.id for s in getattr(p, 'linked_services', []) or []}
            except Exception:
                p_services = set()
            if service_id_set.issubset(p_services):
                capable_pros.append(p)
    else:
        capable_pros = []

    if capable_pros:
        # Disponibilidad por profesional
        grouped: dict[int, list[datetime]] = {}
        for p in capable_pros:
            q = (
                Timeslot.query
                .filter(
                    Timeslot.start >= day_start,
                    Timeslot.start < day_end,
                    Timeslot.status == TimeslotStatus.AVAILABLE,
                    Timeslot.beauty_center_id == center.id,
                    Timeslot.professional_id == p.id,
                )
            )
            # Acotar por servicios cuando el slot traiga service_id
            if service_ids:
                q = q.filter(
                    or_(
                        Timeslot.service_id.is_(None),
                        Timeslot.service_id.in_(service_ids)
                    )
                )
            slots = q.order_by(Timeslot.start).all()

            starts_for_p: list[datetime] = []
            if slots:
                merged: list[tuple[datetime, datetime]] = []
                cur_start = slots[0].start
                cur_end = slots[0].end
                for ts in slots[1:]:
                    if ts.start <= cur_end:
                        if ts.end > cur_end:
                            cur_end = ts.end
                    else:
                        merged.append((cur_start, cur_end))
                        cur_start, cur_end = ts.start, ts.end
                merged.append((cur_start, cur_end))

                for (w_start, w_end) in merged:
                    cursor = w_start
                    # inferir step desde el primer slot del profesional
                    step = 15
                    if slots:
                        step = max(1, int((slots[0].end - slots[0].start).total_seconds() // 60))
                    while cursor + timedelta(minutes=total_duration_min) <= w_end:
                        starts_for_p.append(cursor)
                        cursor += timedelta(minutes=step)

            grouped[p.id] = starts_for_p

        return render_template('partials/_availability_staff.html',
                               center=center,
                               services=services,
                               professionals=capable_pros,
                               grouped_starts=grouped)

    # Fallback sin profesionales configurados: mismo cálculo general del MVP
    q = (
        Timeslot.query
        .filter(
            Timeslot.start >= day_start,
            Timeslot.start < day_end,
            Timeslot.status == TimeslotStatus.AVAILABLE,
            Timeslot.beauty_center_id == center.id,
        )
    )
    slots = q.order_by(Timeslot.start).all()

    available_starts: list[datetime] = []
    if slots:
        merged: list[tuple[datetime, datetime]] = []
        cur_start = slots[0].start
        cur_end = slots[0].end
        for ts in slots[1:]:
            if ts.start <= cur_end:
                if ts.end > cur_end:
                    cur_end = ts.end
            else:
                merged.append((cur_start, cur_end))
                cur_start, cur_end = ts.start, ts.end
        merged.append((cur_start, cur_end))

        for (w_start, w_end) in merged:
            cursor = w_start
            step = 15
            if slots:
                step = max(1, int((slots[0].end - slots[0].start).total_seconds() // 60))
            while cursor + timedelta(minutes=total_duration_min) <= w_end:
                available_starts.append(cursor)
                cursor += timedelta(minutes=step)

    return render_template('partials/_availability.html',
                           center=center,
                           available_starts=available_starts,
                           services=services,
                           message=None)

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


@bp.get('/prof/day_calendar')
def prof_day_calendar():
    """HTMX partial for per-day booking calendar for a Professional.

    Inputs: slug, start (YYYY-MM-DD) optional; shows next 14 days by default.
    """
    from app.models_catalog import Professional, DailyAvailability
    slug = clean_text(request.args.get('slug', ''), 180)
    start_str = request.args.get('start')

    prof = Professional.query.filter_by(slug=slug, is_active=True).first()
    if not prof:
        return render_template('partials/_per_day_calendar.html', professional=None, days=[], message='Profesional no encontrado.')

    # Ensure mode and public visibility
    if getattr(prof, 'booking_mode', 'classic') != 'per_day':
        return render_template('partials/_per_day_calendar.html', professional=prof, days=[], message='Este profesional no acepta reservas por día.')
    if not getattr(prof, 'show_public_booking', True):
        abort(403)

    # Range: next 14 days starting today or provided start
    today = datetime.now().date()
    if start_str and validate_date_format(start_str):
        try:
            base = datetime.strptime(start_str, '%Y-%m-%d').date()
        except ValueError:
            base = today
    else:
        base = today

    window = [base + timedelta(days=i) for i in range(14)]

    # Load existing daily availabilities and default to daily_quota when present
    avail_map = {d.date: d for d in DailyAvailability.query.filter(DailyAvailability.professional_id == prof.id, DailyAvailability.date >= window[0], DailyAvailability.date <= window[-1]).all()}
    days = []
    default_quota = int(getattr(prof, 'daily_quota', 1) or 1)
    for d in window:
        rec = avail_map.get(d)
        if rec:
            days.append({'date': d, 'capacity': int(rec.capacity or 1), 'reserved': int(rec.reserved_count or 0)})
        else:
            # Default: show day with configured quota (0 -> unavailable)
            cap = max(0, default_quota)
            days.append({'date': d, 'capacity': cap, 'reserved': 0})

    return render_template('partials/_per_day_calendar.html', professional=prof, days=days, message=None)


@bp.post('/prof/book_day')
@limiter.limit("5 per minute")
def prof_book_day():
    """HTMX POST: reserve one per-day slot for a Professional on a given date.

    Creates a Subscription with criteria for auditing and increments reserved_count atomically.
    """
    from app.models_catalog import Professional, DailyAvailability
    from app.models import Subscription

    slug = clean_text(request.form.get('slug', ''), 180)
    date_str = request.form.get('date', '')
    email = clean_text(request.form.get('email', '').lower(), 255)

    if not email or not validate_email(email):
        return render_template('partials/_subscription_result.html', success=False, message='Email inválido.')

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return render_template('partials/_subscription_result.html', success=False, message='Fecha inválida.')

    prof = Professional.query.filter_by(slug=slug, is_active=True).first()
    if not prof:
        return render_template('partials/_subscription_result.html', success=False, message='Profesional no encontrado.')

    if getattr(prof, 'booking_mode', 'classic') != 'per_day':
        return render_template('partials/_subscription_result.html', success=False, message='Este profesional no acepta reservas por día.')
    if not getattr(prof, 'show_public_booking', True):
        abort(403)

    # Upsert or lock existing DailyAvailability, then increment reserved_count if capacity allows
    from sqlalchemy import select
    # Try to lock existing record
    rec = (db.session.query(DailyAvailability)
           .filter(DailyAvailability.professional_id == prof.id, DailyAvailability.date == target_date)
           .with_for_update(nowait=False)
           .first())

    if not rec:
        # Create with default capacity from professional.daily_quota
        rec = DailyAvailability(professional_id=prof.id, date=target_date, capacity=int(getattr(prof, 'daily_quota', 1) or 1), reserved_count=0)
        db.session.add(rec)
        db.session.flush()

    if int(rec.reserved_count or 0) >= int(rec.capacity or 0):
        db.session.rollback()
        return render_template('partials/_subscription_result.html', success=False, message='No hay cupos disponibles para ese día.')

    rec.reserved_count = int(rec.reserved_count or 0) + 1

    # Create a criteria subscription for audit/notification purposes
    criteria = {
        'kind': 'per_day',
        'professional_id': prof.id,
        'date': target_date.isoformat(),
    }
    sub = Subscription(email=email, criteria=criteria)
    db.session.add(sub)
    db.session.commit()

    return render_template('partials/_subscription_result.html', success=True, message='Reserva tomada. Te contactaremos para coordinar horario.')

@bp.get('/prof/availability')
def prof_availability():
    """HTMX partial: available start times for a Professional (classic mode).

    Inputs: slug, date (YYYY-MM-DD optional). Shows upcoming day by default.
    """
    from app.models_catalog import Professional

    slug = clean_text(request.args.get('slug', ''), 180)
    date_str = request.args.get('date', '')

    prof = Professional.query.filter_by(slug=slug, is_active=True).first()
    if not prof:
        return render_template('partials/_prof_times.html', professional=None, starts=[], message='Profesional no encontrado.')

    if getattr(prof, 'booking_mode', 'classic') != 'classic':
        return render_template('partials/_prof_times.html', professional=prof, starts=[], message='Este profesional no usa horarios fijos.')
    if not getattr(prof, 'show_public_booking', True):
        abort(403)

    now = datetime.now(timezone.utc)
    q = Timeslot.query.filter(
        Timeslot.status == TimeslotStatus.AVAILABLE,
        Timeslot.professional_id == prof.id,
        Timeslot.start > now,
    )

    # Filtrar por día si se especifica
    if date_str and validate_date_format(date_str):
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
            day_start = datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            q = q.filter(Timeslot.start >= day_start, Timeslot.start < day_end)
        except ValueError:
            pass

    slots = q.order_by(Timeslot.start).all()
    starts = [s.start for s in slots]
    return render_template('partials/_prof_times.html', professional=prof, starts=starts, message=None)
