import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from app.models import Subscription, Timeslot
from app import create_app, db
from jinja2 import Template
import os

def send_notification_email(subscription_id, timeslot_id):
    """Background task to send notification email"""
    # Create app context for database access
    app = create_app()
    
    with app.app_context():
        subscription = Subscription.query.get(subscription_id)
        timeslot = Timeslot.query.get(timeslot_id)
        
        if not subscription or not timeslot:
            return False
        
        try:
            # Prepare email content
            subject, body = _prepare_email_content(subscription, timeslot)
            
            # Send email
            success = _send_email(
                to_email=subscription.email,
                subject=subject,
                body=body
            )
            
            if success:
                app.logger.info(f"Notification email sent to {subscription.email} for timeslot {timeslot_id}")
            else:
                app.logger.error(f"Failed to send notification email to {subscription.email}")
            
            return success
            
        except Exception as e:
            app.logger.error(f"Error sending notification email: {str(e)}")
            return False

def _prepare_email_content(subscription, timeslot):
    """Prepare email subject and body"""
    # Get complex/service info
    if timeslot.field:
        location = f"{timeslot.field.complex.name} - {timeslot.field.name}"
        if timeslot.field.sport:
            location += f" ({timeslot.field.sport})"
    elif timeslot.service:
        location = timeslot.service.name
    else:
        location = "Servicio"
    
    # Format date and time
    fecha = timeslot.start.strftime('%d/%m/%Y')
    hora = timeslot.start.strftime('%H:%M')
    
    # Subject
    subject = f"Se liberó tu turno — {location} {fecha} {hora}"
    
    # Email template
    email_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Turno Disponible - TurnosLibres.com</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #3B82F6; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .button { display: inline-block; background-color: #3B82F6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
        .unsubscribe { color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>¡Tu turno se liberó!</h1>
        </div>
        
        <div class="content">
            <h2>Hola,</h2>
            
            <p>Te avisamos que el turno que estabas esperando ya está disponible:</p>
            
            <div style="background-color: white; padding: 15px; border-left: 4px solid #3B82F6; margin: 20px 0;">
                <strong>{{ location }}</strong><br>
                <strong>Fecha:</strong> {{ fecha }}<br>
                <strong>Hora:</strong> {{ hora }}<br>
                {% if timeslot.price %}
                <strong>Precio:</strong> ${{ timeslot.price }} {{ timeslot.currency }}
                {% endif %}
            </div>
            
            <p>¡Apúrate! Los turnos se reservan rápidamente.</p>
            
            <a href="{{ app_base_url }}" class="button">Ver Turno Disponible</a>
        </div>
        
        <div class="footer">
            <p>Este email fue enviado porque te suscribiste a notificaciones de turnos en TurnosLibres.com</p>
            <p class="unsubscribe">
                <a href="{{ app_base_url }}/unsubscribe/{{ subscription.token_unsubscribe }}">
                    Desuscribirse de estas notificaciones
                </a>
            </p>
        </div>
    </div>
</body>
</html>
    """
    
    # Render template
    template = Template(email_template)
    body = template.render(
        location=location,
        fecha=fecha,
        hora=hora,
        timeslot=timeslot,
        subscription=subscription,
        app_base_url=os.environ.get('APP_BASE_URL', 'http://localhost:8000')
    )
    
    return subject, body

def _send_email(to_email, subject, body):
    """Send email using SMTP"""
    try:
        # Get SMTP configuration
        smtp_host = os.environ.get('SMTP_HOST', 'localhost')
        smtp_port = int(os.environ.get('SMTP_PORT', '1025'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_pass = os.environ.get('SMTP_PASS', '')
        mail_from = os.environ.get('MAIL_FROM', 'no-reply@turnoslibres.com')
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_from
        msg['To'] = to_email
        
        # Add HTML body
        html_part = MIMEText(body, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_user and smtp_pass:
                server.starttls()
                server.login(smtp_user, smtp_pass)
            
            server.send_message(msg)
        
        return True
        
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

def send_test_email(to_email="test@example.com"):
    """Test function to verify email configuration"""
    app = create_app()
    
    with app.app_context():
        try:
            success = _send_email(
                to_email=to_email,
                subject="Test Email - TurnosLibres.com",
                body="<h1>Test Email</h1><p>If you receive this, email configuration is working correctly.</p>"
            )
            
            if success:
                print(f"Test email sent successfully to {to_email}")
            else:
                print("Failed to send test email")
            
            return success
            
        except Exception as e:
            print(f"Error in test email: {str(e)}")
            return False
