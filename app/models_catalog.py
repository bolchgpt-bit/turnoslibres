from datetime import datetime
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy import text
from app import db

# Base común para entidades de catálogo (no usar herencia abstracta de SQLA clásica;
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
    search_vector = db.Column(TSVECTOR)

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


class Professional(db.Model, _CatalogBase):
    __tablename__ = "professionals"
    specialties = db.Column(db.String(240))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    category = db.relationship("Category")
    # Relación de servicios ofrecidos por el profesional
    linked_services = db.relationship("Service", secondary=professional_services)

# índices
db.Index("ix_professionals_search_vector", Professional.search_vector, postgresql_using="gin")
db.Index("ix_professionals_name_ci", text("lower(name)"))

class BeautyCenter(db.Model, _CatalogBase):
    __tablename__ = "beauty_centers"
    services = db.Column(db.String(240))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    category = db.relationship("Category")
    # Relación de servicios ofrecidos por el centro
    linked_services = db.relationship("Service", secondary=beauty_center_services)

db.Index("ix_beauty_centers_search_vector", BeautyCenter.search_vector, postgresql_using="gin")
db.Index("ix_beauty_centers_name_ci", text("lower(name)"))

class SportsComplex(db.Model, _CatalogBase):
    __tablename__ = "sports_complexes"
    sports = db.Column(db.String(240))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    category = db.relationship("Category")

db.Index("ix_sports_complexes_search_vector", SportsComplex.search_vector, postgresql_using="gin")
db.Index("ix_sports_complexes_name_ci", text("lower(name)"))
