from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, ValidationError
from app.models import AppUser
from wtforms import TextAreaField

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message='El email es requerido'),
        Email(message='Ingresa un email válido')
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='La contraseña es requerida')
    ])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message='El email es requerido'),
        Email(message='Ingresa un email válido')
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='La contraseña es requerida'),
        Length(min=6, message='La contraseña debe tener al menos 6 caracteres')
    ])
    password2 = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(message='Confirma tu contraseña')
    ])
    submit = SubmitField('Registrarse')
    
    def validate_email(self, email):
        user = AppUser.query.filter_by(email=email.data.lower()).first()
        if user:
            raise ValidationError('Este email ya está registrado.')
    
    def validate_password2(self, password2):
        if self.password.data != password2.data:
            raise ValidationError('Las contraseñas no coinciden.')


class ProfessionalForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired()])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=180)])
    city = StringField('Ciudad')
    specialties = StringField('Especialidades')
    address = StringField('Dirección')
    phone = StringField('Teléfono')
    website = StringField('Website')
    submit = SubmitField('Crear Profesional')


class BeautyCenterForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired()])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=180)])
    city = StringField('Ciudad')
    services = TextAreaField('Servicios (texto)')
    address = StringField('Dirección')
    phone = StringField('Teléfono')
    website = StringField('Website')
    submit = SubmitField('Crear Centro de Estética')


class SportsComplexForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired()])
    slug = StringField('Slug', validators=[DataRequired(), Length(max=180)])
    city = StringField('Ciudad')
    sports = StringField('Deportes (texto)')
    address = StringField('Dirección')
    phone = StringField('Teléfono')
    website = StringField('Website')
    submit = SubmitField('Crear Complejo Deportivo')
