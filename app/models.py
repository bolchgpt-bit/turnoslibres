from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from sqlalchemy import Index
import uuid
from enum import Enum

class TimeslotStatus(Enum):
    AVAILABLE = 'available'
    HOLDING = 'holding'
    RESERVED = 'reserved'
    BLOCKED = 'blocked'

class SubscriptionStatus(Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    UNSUBSCRIBED = 'unsubscribed'

class AppUser(UserMixin, db.Model):
    __tablename__ = 'app_users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    complexes = db.relationship('Complex', secondary='user_complexes', back_populates='users')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<AppUser {self.email}>'

class Complex(db.Model):
    __tablename__ = 'complexes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text)
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(50))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    users = db.relationship('AppUser', secondary='user_complexes', back_populates='complexes')
    categories = db.relationship('Category', secondary='complex_categories', back_populates='complexes')
    fields = db.relationship('Field', back_populates='complex', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Complex {self.name}>'

class UserComplex(db.Model):
    __tablename__ = 'user_complexes'
    
    user_id = db.Column(db.Integer, db.ForeignKey('app_users.id'), primary_key=True)
    complex_id = db.Column(db.Integer, db.ForeignKey('complexes.id'), primary_key=True)

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    complexes = db.relationship('Complex', secondary='complex_categories', back_populates='categories')
    services = db.relationship('Service', back_populates='category', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Category {self.title}>'

class ComplexCategory(db.Model):
    __tablename__ = 'complex_categories'
    
    complex_id = db.Column(db.Integer, db.ForeignKey('complexes.id'), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), primary_key=True)

class Service(db.Model):
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), nullable=False)
    duration_min = db.Column(db.Integer, nullable=False)
    base_price = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='ARS')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    category = db.relationship('Category', back_populates='services')
    timeslots = db.relationship('Timeslot', back_populates='service')
    
    # Unique constraint per category
    __table_args__ = (
        db.UniqueConstraint('category_id', 'slug', name='uq_service_category_slug'),
    )
    
    def __repr__(self):
        return f'<Service {self.name}>'

class Field(db.Model):
    __tablename__ = 'fields'
    
    id = db.Column(db.Integer, primary_key=True)
    complex_id = db.Column(db.Integer, db.ForeignKey('complexes.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    sport = db.Column(db.String(100))
    surface = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    complex = db.relationship('Complex', back_populates='fields')
    timeslots = db.relationship('Timeslot', back_populates='field')
    
    def __repr__(self):
        return f'<Field {self.name}>'

class Timeslot(db.Model):
    __tablename__ = 'timeslots'
    
    id = db.Column(db.Integer, primary_key=True)
    field_id = db.Column(db.Integer, db.ForeignKey('fields.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    start = db.Column(db.DateTime(timezone=True), nullable=False)
    end = db.Column(db.DateTime(timezone=True), nullable=False)
    price = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='ARS')
    status = db.Column(db.Enum(TimeslotStatus), default=TimeslotStatus.AVAILABLE, nullable=False)
    reservation_code = db.Column(db.String(50))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    field = db.relationship('Field', back_populates='timeslots')
    service = db.relationship('Service', back_populates='timeslots')
    subscriptions = db.relationship('Subscription', back_populates='timeslot')
    
    # Indexes
    __table_args__ = (
        Index('ix_timeslot_start_status', 'start', 'status'),
        Index('ix_timeslot_field_id', 'field_id'),
        Index('ix_timeslot_service_id', 'service_id'),
    )
    
    def __repr__(self):
        return f'<Timeslot {self.start} - {self.status.value}>'

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    timeslot_id = db.Column(db.Integer, db.ForeignKey('timeslots.id'), nullable=True)
    field_id = db.Column(db.Integer, db.ForeignKey('fields.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    start_window = db.Column(db.DateTime(timezone=True), nullable=True)
    end_window = db.Column(db.DateTime(timezone=True), nullable=True)
    token_unsubscribe = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    status = db.Column(db.Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    timeslot = db.relationship('Timeslot', back_populates='subscriptions')
    
    # Indexes
    __table_args__ = (
        Index('ix_subscription_timeslot_id', 'timeslot_id'),
        Index('ix_subscription_field_window', 'field_id', 'start_window', 'end_window'),
        Index('ix_subscription_email', 'email'),
    )
    
    def __repr__(self):
        return f'<Subscription {self.email} - {self.status.value}>'
