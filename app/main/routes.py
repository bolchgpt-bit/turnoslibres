from flask import render_template, request, jsonify, flash, redirect, url_for
from app.main import bp
from app.models import Category, Complex, Timeslot, Field, Service
from app.models_catalog import BeautyCenter, Professional
from app.utils import validate_category, clean_text
from app import db
from datetime import datetime, timedelta
import re

@bp.route('/')
def index():
    """Homepage with three category cards"""
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('main/index.html', categories=categories)

@bp.route('/<category>')
def category_page(category):
    """Category landing pages with allow-list validation"""
    if not validate_category(category):
        flash('Categoría no válida.', 'error')
        return redirect(url_for('main.index'))
    
    category_obj = Category.query.filter_by(slug=category, is_active=True).first()
    if not category_obj:
        flash('Categoría no encontrada.', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('main/category.html', category=category_obj)

@bp.route('/complejos/<slug>')
def complex_detail(slug):
    """Complex detail page"""
    complex_obj = Complex.query.filter_by(slug=slug).first_or_404()
    return render_template('main/complex.html', complex=complex_obj)

@bp.route('/centros/<slug>')
def beauty_center_detail(slug):
    """Beauty center detail page"""
    center = BeautyCenter.query.filter_by(slug=slug).first_or_404()
    return render_template('main/beauty_center.html', center=center)

@bp.route('/r/<slug>')
def vanity_resolver(slug):
    """Resolve single-segment vanity slugs to the right detail page.

    Order: Complex -> BeautyCenter. Extendable to Professional.
    """
    c = Complex.query.filter_by(slug=slug).first()
    if c:
        return redirect(url_for('main.complex_detail', slug=slug), code=302)
    b = BeautyCenter.query.filter_by(slug=slug).first()
    if b:
        return redirect(url_for('main.beauty_center_detail', slug=slug), code=302)
    p = Professional.query.filter_by(slug=slug).first()
    if p:
        return redirect(url_for('main.professional_detail', slug=slug), code=302)
    flash('Página no encontrada.', 'error')
    return redirect(url_for('main.index'))

@bp.route('/publicar')
def publish():
    """Lead generation form for businesses"""
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('main/publish.html', categories=categories)

@bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    """Unsubscribe from waitlist notifications"""
    from app.models import Subscription, SubscriptionStatus
    
    subscription = Subscription.query.filter_by(token_unsubscribe=token).first()
    if not subscription:
        flash('Token de desuscripción no válido.', 'error')
        return redirect(url_for('main.index'))
    
    if subscription.status != SubscriptionStatus.UNSUBSCRIBED:
        subscription.status = SubscriptionStatus.UNSUBSCRIBED
        db.session.commit()
        flash('Te has desuscrito correctamente de las notificaciones.', 'success')
    else:
        flash('Ya estás desuscrito de las notificaciones.', 'info')
    
    return render_template('main/unsubscribe.html', subscription=subscription)

@bp.route('/profesionales/<slug>')
def professional_detail(slug):
    """Professional detail page (classic or per-day mode)."""
    prof = Professional.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template('main/professional.html', professional=prof)
