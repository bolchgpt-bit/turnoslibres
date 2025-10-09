from app import create_app, db
from app.models import Timeslot, Subscription


def main():
    app = create_app()
    with app.app_context():
        # Borra primero suscripciones que referencian turnos
        subs_deleted = db.session.query(Subscription).delete(synchronize_session=False)
        # Luego borra todos los turnos
        ts_deleted = db.session.query(Timeslot).delete(synchronize_session=False)
        db.session.commit()
        print(f"Eliminados: subscriptions={subs_deleted}, timeslots={ts_deleted}")


if __name__ == "__main__":
    main()

