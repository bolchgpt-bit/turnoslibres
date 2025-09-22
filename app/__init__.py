from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from rq import Queue
import os
from app.security import security_headers, generate_csrf_token

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

def create_app(config_name=None):
    app = Flask(__name__)
    
    # Configuration
    if config_name:
        app.config.update(config_name)
    else:
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://postgres:postgres@localhost:5432/turnos')
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['WTF_CSRF_TIME_LIMIT'] = None
    
    # Redis configuration
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    app.config['REDIS_URL'] = redis_url
    
    # Email configuration
    app.config['SMTP_HOST'] = os.environ.get('SMTP_HOST', 'localhost')
    app.config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', '1025'))
    app.config['SMTP_USER'] = os.environ.get('SMTP_USER', '')
    app.config['SMTP_PASS'] = os.environ.get('SMTP_PASS', '')
    app.config['MAIL_FROM'] = os.environ.get('MAIL_FROM', 'no-reply@turnoslibres.com')
    app.config['APP_BASE_URL'] = os.environ.get('APP_BASE_URL', 'http://localhost:8000')
    
    # Hold configuration
    app.config['HOLD_MINUTES'] = int(os.environ.get('HOLD_MINUTES', '15'))
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Login manager configuration
    login_manager.login_view = 'admin.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'info'
    
    # Initialize Redis and RQ
    redis_conn = redis.from_url(redis_url)
    app.redis = redis_conn
    app.task_queue = Queue('notify:emails', connection=redis_conn)
    
    # Security headers
    @app.after_request
    def apply_security_headers(response):
        return security_headers(response)
    
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf_token)
    
    # Register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    from app.ui import bp as ui_bp
    app.register_blueprint(ui_bp, url_prefix='/ui')
    
    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import AppUser
    return AppUser.query.get(int(user_id))
