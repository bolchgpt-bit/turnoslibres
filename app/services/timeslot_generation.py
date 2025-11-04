from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Tuple

from app import db
from app.models import Timeslot, TimeslotStatus, Field
from app.models_catalog import Professional


def generate_timeslots_for_field(
    *,
    field: Field,
    start_date: date,
    end_date: date,
    start_time: time,
    end_time: time,
    duration_min: int,
    interval_min: int,
    weekdays: Iterable[int],
    price: float | None,
    currency: str = "ARS",
    status: TimeslotStatus = TimeslotStatus.AVAILABLE,
) -> Tuple[int, int]:
    """Generate timeslots in bulk for a Field within a window.

    Returns a tuple (created_count, skipped_count).
    """
    created = 0
    skipped = 0
    weekdays_set = set(int(w) for w in weekdays)

    # Normalize window
    if duration_min <= 0 or interval_min <= 0:
        return (0, 0)
    if end_date < start_date:
        return (0, 0)
    if end_time <= start_time:
        return (0, 0)

    # Iterate date range
    days = (end_date - start_date).days + 1
    for d in range(days):
        day = start_date + timedelta(days=d)
        if day.weekday() not in weekdays_set:
            continue

        # Compose first start
        start_dt = datetime.combine(day, start_time)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt_limit = datetime.combine(day, end_time)
        if end_dt_limit.tzinfo is None:
            end_dt_limit = end_dt_limit.replace(tzinfo=timezone.utc)

        # For each slot within time window
        i = 0
        while True:
            slot_start = start_dt + timedelta(minutes=i * interval_min)
            slot_end = slot_start + timedelta(minutes=duration_min)
            if slot_end > end_dt_limit:
                break

            # Avoid overlap on the same field
            overlap = (
                Timeslot.query
                .filter(
                    Timeslot.field_id == field.id,
                    Timeslot.start < slot_end,
                    Timeslot.end > slot_start,
                )
                .first()
            )
            if overlap:
                skipped += 1
            else:
                ts = Timeslot(
                    field_id=field.id,
                    start=slot_start,
                    end=slot_end,
                    price=price,
                    currency=currency,
                    status=status,
                )
                db.session.add(ts)
                created += 1

            i += 1

    db.session.commit()
    return (created, skipped)


def generate_timeslots_for_professional(
    *,
    professional: Professional,
    service_id: int,
    start_date: date,
    end_date: date,
    start_time: time,
    end_time: time,
    duration_min: int,
    interval_min: int | None,
    weekdays: Iterable[int],
    price: float | None,
    currency: str = "ARS",
    status: TimeslotStatus = TimeslotStatus.AVAILABLE,
) -> Tuple[int, int]:
    """Generate timeslots for a Professional within a window for a given service.

    - Avoids overlaps on the same professional.
    - If interval_min is None or <=0, uses duration_min as step.
    Returns (created, skipped).
    """
    created = 0
    skipped = 0
    weekdays_set = set(int(w) for w in weekdays)

    if duration_min <= 0:
        return (0, 0)
    step = int(interval_min or duration_min)
    if step <= 0:
        step = duration_min

    if end_date < start_date:
        return (0, 0)
    if end_time <= start_time:
        return (0, 0)

    days = (end_date - start_date).days + 1
    for d in range(days):
        day = start_date + timedelta(days=d)
        if day.weekday() not in weekdays_set:
            continue

        start_dt = datetime.combine(day, start_time)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt_limit = datetime.combine(day, end_time)
        if end_dt_limit.tzinfo is None:
            end_dt_limit = end_dt_limit.replace(tzinfo=timezone.utc)

        i = 0
        while True:
            slot_start = start_dt + timedelta(minutes=i * step)
            slot_end = slot_start + timedelta(minutes=duration_min)
            if slot_end > end_dt_limit:
                break

            overlap = (
                Timeslot.query
                .filter(
                    Timeslot.professional_id == professional.id,
                    Timeslot.start < slot_end,
                    Timeslot.end > slot_start,
                )
                .first()
            )
            if overlap:
                skipped += 1
            else:
                ts = Timeslot(
                    professional_id=professional.id,
                    service_id=service_id,
                    start=slot_start,
                    end=slot_end,
                    price=price,
                    currency=currency,
                    status=status,
                )
                db.session.add(ts)
                created += 1

            i += 1

    db.session.commit()
    return (created, skipped)
