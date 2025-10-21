from flask import current_app
from app.models import Subscription, Timeslot, SubscriptionStatus, TimeslotStatus
from app import db
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template

class NotificationService:
    """Service for handling waitlist notifications"""
    
    @staticmethod
    def notify_timeslot_available(timeslot_id):
        """Notify subscribers when a timeslot becomes available"""
        timeslot = Timeslot.query.get(timeslot_id)
        if not timeslot or timeslot.status != TimeslotStatus.AVAILABLE:
            return
        
        # Find active subscriptions for this timeslot
        subscriptions = Subscription.query.filter(
            Subscription.timeslot_id == timeslot_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.is_active.is_(True),
        ).all()
        
        # Also find subscriptions by criteria (field/service + time window)
        criteria_subscriptions = []
        if timeslot.field_id:
            criteria_subscriptions = Subscription.query.filter(
                Subscription.field_id == timeslot.field_id,
                Subscription.timeslot_id.is_(None),
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.is_active.is_(True),
                Subscription.start_window <= timeslot.start,
                Subscription.end_window >= timeslot.end
            ).all()

        elif timeslot.service_id:
            criteria_subscriptions = Subscription.query.filter(
                Subscription.service_id == timeslot.service_id,
                Subscription.timeslot_id.is_(None),
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.is_active.is_(True),
                Subscription.start_window <= timeslot.start,
                Subscription.end_window >= timeslot.end
            ).all()

        
        all_subscriptions = subscriptions + criteria_subscriptions
        
        # Queue email notifications
        for subscription in all_subscriptions:
            current_app.task_queue.enqueue(
                'app.workers.email_worker.send_notification_email',
                subscription.id,
                timeslot_id,
                job_timeout='5m'
            )
    
    @staticmethod
    def create_timeslot_subscription(email, timeslot_id):
        """Create a subscription for a specific timeslot"""
        # Check if already subscribed
        existing = Subscription.query.filter(
            Subscription.email == email,
            Subscription.timeslot_id == timeslot_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.is_active.is_(True),
        ).first()
        
        if existing:
            return False, "Ya estás suscrito a este turno."
        
        # Create subscription
        subscription = Subscription(
            email=email,
            timeslot_id=timeslot_id
        )
        db.session.add(subscription)
        db.session.commit()
        
        return True, "Suscripción exitosa."
    
    @staticmethod
    def create_criteria_subscription(email, field_id=None, service_id=None, start_window=None, end_window=None):
        """Create a subscription based on criteria (field/service + time window)"""
        subscription = Subscription(
            email=email,
            field_id=field_id,
            service_id=service_id,
            start_window=start_window,
            end_window=end_window
        )
        db.session.add(subscription)
        db.session.commit()
        
        return True, "Suscripción por criterio creada exitosamente."
