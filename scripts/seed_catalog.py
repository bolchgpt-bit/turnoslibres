import argparse
from datetime import datetime, timezone
from sqlalchemy import text
from flask import current_app
from app import create_app, db
from app.models_catalog import Professional, BeautyCenter, SportsComplex
from app.models import Category


def seed_professionals() -> int:
    """Inserta profesionales de ejemplo y devuelve la cantidad insertada."""
    cat = Category.query.filter_by(slug='profesionales').first()
    rows = [
        Professional(
            name="Dra. Ana Kinesióloga",
            slug="ana-kinesiologa",
            city="Buenos Aires",
            specialties="Kinesiología deportiva",
            address="Av. Cabildo 1234",
            phone="+54 11 5555-1111",
            website="https://ejemplo-ana.com",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category_id=cat.id if cat else None,
        ),
        Professional(
            name="Lic. Martín Nutricionista",
            slug="martin-nutricionista",
            city="Córdoba",
            specialties="Nutrición clínica y deportiva",
            address="Bv. San Juan 900",
            phone="+54 351 555-2222",
            website="https://ejemplo-martin.com",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category_id=cat.id if cat else None,
        ),
    ]
    db.session.bulk_save_objects(rows)
    db.session.flush()
    return len(rows)


def seed_beauty_centers() -> int:
    """Inserta centros de estética de ejemplo y devuelve la cantidad."""
    cat = Category.query.filter_by(slug='estetica').first()
    rows = [
        BeautyCenter(
            name="Glow Estética",
            slug="glow-estetica",
            city="Rosario",
            services="Limpieza facial, Depilación, Masajes",
            address="Mitre 456",
            phone="+54 341 555-3333",
            website="https://glow-estetica.com",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category_id=cat.id if cat else None,
        ),
        BeautyCenter(
            name="Belleza Zen",
            slug="belleza-zen",
            city="Mendoza",
            services="Radiofrecuencia, Drenaje linfático",
            address="Av. Colón 150",
            phone="+54 261 555-4444",
            website="https://bellezazen.com",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category_id=cat.id if cat else None,
        ),
    ]
    db.session.bulk_save_objects(rows)
    db.session.flush()
    return len(rows)


def seed_sports_complexes() -> int:
    """Inserta complejos deportivos de ejemplo y devuelve la cantidad."""
    cat = Category.query.filter_by(slug='deportes').first()
    rows = [
        SportsComplex(
            name="Complejo Fútbol Park",
            slug="complejo-futbol-park",
            city="Buenos Aires",
            sports="Fútbol 5, Fútbol 7",
            address="Crovara 1000",
            phone="+54 11 5555-5555",
            website="https://futbolpark.com",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category_id=cat.id if cat else None,
        ),
        SportsComplex(
            name="MultiSport Arena",
            slug="multisport-arena",
            city="La Plata",
            sports="Pádel, Básquet",
            address="7 y 50",
            phone="+54 221 555-6666",
            website="https://multisport.ar",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            category_id=cat.id if cat else None,
        ),
    ]
    db.session.bulk_save_objects(rows)
    db.session.flush()
    return len(rows)


def reset_tables(engine) -> None:
    """Vacía las tablas del catálogo de forma segura e intenta reiniciar secuencias."""
    # Seguro e idempotente: si estás en Postgres, TRUNCATE es rapidísimo
    # Si usás otro motor, el DELETE fallback también sirve.
    try:
        db.session.execute(text(
            "TRUNCATE TABLE professionals, beauty_centers, sports_complexes RESTART IDENTITY CASCADE;"
        ))
    except Exception:
        # Fallback genérico
        db.session.execute(text("DELETE FROM professionals;"))
        db.session.execute(text("DELETE FROM beauty_centers;"))
        db.session.execute(text("DELETE FROM sports_complexes;"))
        # Reiniciar IDs si querés (Postgres)
        try:
            db.session.execute(text("ALTER SEQUENCE professionals_id_seq RESTART WITH 1;"))
            db.session.execute(text("ALTER SEQUENCE beauty_centers_id_seq RESTART WITH 1;"))
            db.session.execute(text("ALTER SEQUENCE sports_complexes_id_seq RESTART WITH 1;"))
        except Exception as e:
            # Silently continue if sequences don't exist on the current DB engine
            try:
                current_app.logger.debug("Sequence reset skipped: %s", str(e))
            except Exception:
                # In case current_app is not available, avoid breaking the script
                pass
    db.session.commit()


def main() -> None:
    """CLI principal: parsea argumentos, resetea opcionalmente y ejecuta seeds."""
    parser = argparse.ArgumentParser(description="Seed de entidades de catálogo")
    parser.add_argument("--reset", action="store_true", help="Vacía tablas antes de insertar")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.reset:
            print("- Limpiando tablas (professionals, beauty_centers, sports_complexes)...")
            reset_tables(db.engine)

        print("- Insertando professionals...")
        n1 = seed_professionals()

        print("- Insertando beauty_centers...")
        n2 = seed_beauty_centers()

        print("- Insertando sports_complexes...")
        n3 = seed_sports_complexes()

        db.session.commit()
        print(f"Listo. Insertados: professionals={n1}, beauty_centers={n2}, sports_complexes={n3}")

        # Verificación simple
        p_count = db.session.query(Professional).count()
        b_count = db.session.query(BeautyCenter).count()
        s_count = db.session.query(SportsComplex).count()
        print(f"Totales en BD: professionals={p_count}, beauty_centers={b_count}, sports_complexes={s_count}")


if __name__ == "__main__":
    main()

