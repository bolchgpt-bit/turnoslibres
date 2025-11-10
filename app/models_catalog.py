from datetime import datetime
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy import text
from sqlalchemy.types import TypeDecorator, TEXT
from app import db
# Compatibilidad: TSVECTOR en Postgres, TEXT en SQLite (para CI/tests)
class TSVectorCompat(TypeDecorator):
    impl = TEXT
    cache_ok = True
    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(TEXT())

# Base comÃºn para entidades de catÃ¡logo (no usar herencia abstracta de SQLA clÃ¡sica;
# en Flask-SQLAlchemy cada modelo hereda de db.Model directamente).
class _CatalogBase:
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), nullable=False, unique=True)
    city = db.Column(db.String(120), index=True)
    address = db.Column(db.String(200))
    phone = db.Column(db.String(60))
    website = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    # Full-Text Search (PostgreSQL)
    search_vector = db.Column(TSVectorCompat())

professional_services = db.Table(
    "professional_services",
    db.Column("professional_id", db.Integer, db.ForeignKey("professionals.id"), primary_key=True),
    db.Column("service_id", db.Integer, db.ForeignKey("services.id"), primary_key=True),
)

beauty_center_services = db.Table(
    "beauty_center_services",
    db.Column("beauty_center_id", db.Integer, db.ForeignKey("beauty_centers.id"), primary_key=True),
    db.Column("service_id", db.Integer, db.ForeignKey("services.id"), primary_key=True),
)


# VinculaciÃ³n de profesionales (staff) con centros de estÃ©tica
beauty_center_professionals = db.Table(
    "beauty_center_professionals",
    db.Column("beauty_center_id", db.Integer, db.ForeignKey("beauty_centers.id"), primary_key=True),
    db.Column("professional_id", db.Integer, db.ForeignKey("professionals.id"), primary_key=True),
)


class Professional(db.Model, _CatalogBase):
    __tablename__ = "professionals"
    specialties = db.Column(db.String(240))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    category = db.relationship("Category")
    # RelaciÃ³n de servicios ofrecidos por el profesional
    linked_services = db.relationship("Service", secondary=professional_services)
    # ConfiguraciÃ³n de reservas del profesional
    booking_mode = db.Column(db.Enum('classic', 'per_day', name='booking_mode_enum'), nullable=False, server_default='classic')
    slot_duration_min = db.Column(db.Integer, nullable=True)
    daily_quota = db.Column(db.Integer, nullable=True)
    show_public_booking = db.Column(db.Boolean, nullable=False, server_default='1')


# Ã­ndices
db.Index("ix_professionals_search_vector", Professional.search_vector, postgresql_using="gin")
db.Index("ix_professionals_name_ci", text("lower(name)"))

class BeautyCenter(db.Model, _CatalogBase):
    __tablename__ = "beauty_centers"
    services = db.Column(db.String(240))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    category = db.relationship("Category")
    # RelaciÃ³n de servicios ofrecidos por el centro
    linked_services = db.relationship("Service", secondary=beauty_center_services)
    show_public_booking = db.Column(db.Boolean, nullable=False, server_default='1')
    # Modo de reserva a nivel negocio (centro): flexible o fijo a un servicio
    booking_mode = db.Column(db.Enum('flexible', 'fixed', name='beauty_center_booking_mode_enum'), nullable=False, server_default='flexible')
    fixed_service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True, index=True)
    fixed_service = db.relationship('Service', foreign_keys=[fixed_service_id])


db.Index("ix_beauty_centers_search_vector", BeautyCenter.search_vector, postgresql_using="gin")
db.Index("ix_beauty_centers_name_ci", text("lower(name)"))


# Relaciones adicionales declarativas entre Professional y BeautyCenter
Professional.beauty_centers = db.relationship("BeautyCenter", secondary="beauty_center_professionals", back_populates="professionals")  # type: ignore[name-defined]
BeautyCenter.professionals = db.relationship("Professional", secondary="beauty_center_professionals", back_populates="beauty_centers")  # type: ignore[name-defined]

class BeautyCenterPhoto(db.Model):
    __tablename__ = "beauty_center_photos"
    id = db.Column(db.Integer, primary_key=True)
    beauty_center_id = db.Column(db.Integer, db.ForeignKey('beauty_centers.id'), nullable=False, index=True)
    path = db.Column(db.String(300), nullable=False)
    rank = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# backref relation for photos
BeautyCenter.photos = db.relationship('BeautyCenterPhoto', backref='beauty_center', cascade='all, delete-orphan', order_by='BeautyCenterPhoto.rank')

class SportsComplex(db.Model, _CatalogBase):
    __tablename__ = "sports_complexes"
    sports = db.Column(db.String(240))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    category = db.relationship("Category")

db.Index("ix_sports_complexes_search_vector", SportsComplex.search_vector, postgresql_using="gin")
db.Index("ix_sports_complexes_name_ci", text("lower(name)"))


class DailyAvailability(db.Model):
    __tablename__ = 'daily_availabilities'
    id = db.Column(db.Integer, primary_key=True)
    professional_id = db.Column(db.Integer, db.ForeignKey('professionals.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=1)
    reserved_count = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.String(280))

    professional = db.relationship('Professional')

    __table_args__ = (
        db.UniqueConstraint('professional_id', 'date', name='uq_daily_prof_date'),
        db.Index('ix_daily_date', 'date'),
    )

