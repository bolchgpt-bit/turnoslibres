import argparse
from datetime import datetime, timedelta, timezone, time as dtime
from decimal import Decimal

from app import create_app, db
from app.models import Timeslot, TimeslotStatus, Field, Service


def parse_time(s: str) -> dtime:
    try:
        return datetime.strptime(s, "%H:%M").time()
    except ValueError:
        raise argparse.ArgumentTypeError("Formato de hora inválido. Usa HH:MM, ej. 09:30")


def main():
    parser = argparse.ArgumentParser(description="Crear turnos de prueba futuros para un campo o servicio")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--field-id", type=int, help="ID de Field (deportes)")
    group.add_argument("--service-id", type=int, help="ID de Service (estética/profesionales)")

    parser.add_argument("--slots", type=int, default=5, help="Cantidad de turnos a crear (por día)")
    parser.add_argument("--duration", type=int, default=60, help="Duración de cada turno en minutos")
    parser.add_argument("--interval", type=int, default=None, help="Minutos entre inicios. Por defecto = duración")
    parser.add_argument("--start", type=parse_time, default=None, help="Hora inicial HH:MM. Por defecto: ahora redondeado + 15 min")
    parser.add_argument("--days", type=int, default=1, help="Número de días consecutivos a generar (desde hoy)")
    parser.add_argument("--price", type=str, default=None, help="Precio por turno. Si no se indica, usa base_price del servicio o 0")
    parser.add_argument("--currency", type=str, default="ARS", help="Moneda (por defecto ARS)")
    parser.add_argument("--status", type=str, choices=[s.value for s in TimeslotStatus], default=TimeslotStatus.AVAILABLE.value,
                        help="Estado del turno (por defecto available)")

    args = parser.parse_args()
    interval = args.interval or args.duration

    app = create_app()
    with app.app_context():
        # Validar destino (field/service)
        target_field = None
        target_service = None
        if args.field_id:
            target_field = Field.query.get(args.field_id)
            if not target_field:
                raise SystemExit(f"Field id={args.field_id} no encontrado")
        if args.service_id:
            target_service = Service.query.get(args.service_id)
            if not target_service:
                raise SystemExit(f"Service id={args.service_id} no encontrado")

        # Calcular hora inicial base futura
        now_utc = datetime.now(timezone.utc)

        if args.start is None:
            # Redondear a próximo múltiplo de 15 min para comenzar
            minute = (now_utc.minute // 15 + 1) * 15
            add_minutes = (minute - now_utc.minute) % 60
            base_time = (now_utc + timedelta(minutes=add_minutes)).time().replace(second=0, microsecond=0)
        else:
            base_time = args.start

        # Precio
        if args.price is not None:
            try:
                price = Decimal(args.price)
            except Exception:
                raise SystemExit("Precio inválido. Usa un número, ej. 3500 o 3500.00")
        else:
            price = Decimal(str(getattr(target_service, 'base_price', 0) or 0))

        status = TimeslotStatus(args.status)

        created = 0
        for day_offset in range(args.days):
            day = (now_utc + timedelta(days=day_offset)).date()
            # Construir datetime inicial (con zona UTC para coincidir con columnas timezone=True)
            start_dt = datetime.combine(day, base_time)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)

            # Asegurar que el primer slot esté en el futuro
            if start_dt <= now_utc:
                start_dt = now_utc + timedelta(minutes=15)
                start_dt = start_dt.replace(second=0, microsecond=0)

            for i in range(args.slots):
                slot_start = start_dt + timedelta(minutes=i * interval)
                slot_end = slot_start + timedelta(minutes=args.duration)

                # Evitar duplicados exactos
                q = Timeslot.query.filter(Timeslot.start == slot_start, Timeslot.end == slot_end)
                if target_field:
                    q = q.filter(Timeslot.field_id == target_field.id)
                if target_service:
                    q = q.filter(Timeslot.service_id == target_service.id)
                if q.first():
                    continue

                ts = Timeslot(
                    field_id=target_field.id if target_field else None,
                    service_id=target_service.id if target_service else None,
                    start=slot_start,
                    end=slot_end,
                    price=price,
                    currency=args.currency,
                    status=status,
                )
                db.session.add(ts)
                created += 1

        db.session.commit()
        print(f"Listo. Turnos creados: {created}")


if __name__ == "__main__":
    main()

