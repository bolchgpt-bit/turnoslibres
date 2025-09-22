from app import create_app, db
from app.models import Category, Complex, Field, Service, Timeslot, AppUser, UserComplex, TimeslotStatus
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import random

def seed_database():
    """Seed the database with initial data"""
    app = create_app()
    
    with app.app_context():
        print("Seeding database...")
        
        # Create categories
        categories_data = [
            {'slug': 'deportes', 'title': 'Deportes', 'description': 'Canchas y espacios deportivos'},
            {'slug': 'estetica', 'title': 'Estética', 'description': 'Peluquerías, barberías y centros de belleza'},
            {'slug': 'profesionales', 'title': 'Profesionales', 'description': 'Servicios profesionales de salud, educación y consultoría'}
        ]
        
        categories = {}
        for cat_data in categories_data:
            category = Category.query.filter_by(slug=cat_data['slug']).first()
            if not category:
                category = Category(**cat_data)
                db.session.add(category)
                db.session.flush()
            categories[cat_data['slug']] = category
        
        # Create complexes
        complexes_data = [
            # Deportes
            {'name': 'Club Deportivo Central', 'slug': 'club-central', 'city': 'Buenos Aires', 'category': 'deportes'},
            {'name': 'Complejo Futbol 5 Norte', 'slug': 'futbol5-norte', 'city': 'Córdoba', 'category': 'deportes'},
            
            # Estética
            {'name': 'Salón Belleza Total', 'slug': 'belleza-total', 'city': 'Buenos Aires', 'category': 'estetica'},
            {'name': 'Barbería Clásica', 'slug': 'barberia-clasica', 'city': 'Rosario', 'category': 'estetica'},
            
            # Profesionales
            {'name': 'Centro Médico Integral', 'slug': 'centro-medico', 'city': 'Buenos Aires', 'category': 'profesionales'},
            {'name': 'Consultorio Psicológico', 'slug': 'consultorio-psi', 'city': 'Mendoza', 'category': 'profesionales'}
        ]
        
        complexes = {}
        for comp_data in complexes_data:
            complex_obj = Complex.query.filter_by(slug=comp_data['slug']).first()
            if not complex_obj:
                complex_obj = Complex(
                    name=comp_data['name'],
                    slug=comp_data['slug'],
                    city=comp_data['city'],
                    address=f"Dirección de {comp_data['name']}",
                    contact_email=f"info@{comp_data['slug'].replace('-', '')}.com",
                    contact_phone=f"+54 11 {random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
                )
                db.session.add(complex_obj)
                db.session.flush()
                
                # Link to category
                category = categories[comp_data['category']]
                complex_obj.categories.append(category)
            
            complexes[comp_data['slug']] = complex_obj
        
        # Create services for non-sports categories
        services_data = [
            # Estética
            {'name': 'Corte de Cabello', 'slug': 'corte-cabello', 'category': 'estetica', 'duration': 30, 'price': 2500},
            {'name': 'Coloración', 'slug': 'coloracion', 'category': 'estetica', 'duration': 90, 'price': 8000},
            {'name': 'Manicura', 'slug': 'manicura', 'category': 'estetica', 'duration': 45, 'price': 3000},
            {'name': 'Barba y Bigote', 'slug': 'barba-bigote', 'category': 'estetica', 'duration': 20, 'price': 1500},
            
            # Profesionales
            {'name': 'Consulta Médica General', 'slug': 'consulta-medica', 'category': 'profesionales', 'duration': 30, 'price': 5000},
            {'name': 'Sesión Psicológica', 'slug': 'sesion-psicologica', 'category': 'profesionales', 'duration': 50, 'price': 6000},
            {'name': 'Consulta Nutricional', 'slug': 'consulta-nutricional', 'category': 'profesionales', 'duration': 40, 'price': 4500},
            {'name': 'Terapia Física', 'slug': 'terapia-fisica', 'category': 'profesionales', 'duration': 60, 'price': 7000}
        ]
        
        services = {}
        for serv_data in services_data:
            service = Service.query.filter_by(slug=serv_data['slug'], category_id=categories[serv_data['category']].id).first()
            if not service:
                service = Service(
                    name=serv_data['name'],
                    slug=serv_data['slug'],
                    category_id=categories[serv_data['category']].id,
                    duration_min=serv_data['duration'],
                    base_price=serv_data['price'],
                    currency='ARS'
                )
                db.session.add(service)
                db.session.flush()
            services[serv_data['slug']] = service
        
        # Create fields for sports complexes
        fields_data = [
            {'name': 'Cancha 1', 'complex': 'club-central', 'sport': 'Fútbol 11'},
            {'name': 'Cancha 2', 'complex': 'club-central', 'sport': 'Fútbol 11'},
            {'name': 'Cancha Tenis 1', 'complex': 'club-central', 'sport': 'Tenis'},
            {'name': 'Cancha A', 'complex': 'futbol5-norte', 'sport': 'Fútbol 5'},
            {'name': 'Cancha B', 'complex': 'futbol5-norte', 'sport': 'Fútbol 5'},
            {'name': 'Cancha C', 'complex': 'futbol5-norte', 'sport': 'Fútbol 5'}
        ]
        
        fields = {}
        for field_data in fields_data:
            field = Field.query.filter_by(name=field_data['name'], complex_id=complexes[field_data['complex']].id).first()
            if not field:
                field = Field(
                    name=field_data['name'],
                    complex_id=complexes[field_data['complex']].id,
                    sport=field_data['sport'],
                    surface='Césped sintético'
                )
                db.session.add(field)
                db.session.flush()
            fields[f"{field_data['complex']}-{field_data['name']}"] = field
        
        # Create admin users
        admin_email = 'admin@turnoslibres.com'
        admin_user = AppUser.query.filter_by(email=admin_email).first()
        if not admin_user:
            admin_user = AppUser(
                email=admin_email,
                is_superadmin=True
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.flush()
        
        # Create regular admin user
        regular_admin_email = 'manager@club-central.com'
        regular_admin = AppUser.query.filter_by(email=regular_admin_email).first()
        if not regular_admin:
            regular_admin = AppUser(email=regular_admin_email)
            regular_admin.set_password('manager123')
            db.session.add(regular_admin)
            db.session.flush()
            
            # Link to complex
            user_complex = UserComplex(
                user_id=regular_admin.id,
                complex_id=complexes['club-central'].id
            )
            db.session.add(user_complex)
        
        # Create timeslots
        print("Creating timeslots...")
        base_date = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        
        # Sports timeslots
        for i in range(14):  # 2 weeks
            current_date = base_date + timedelta(days=i)
            
            for field_key, field in fields.items():
                # Create slots every 2 hours from 8 AM to 10 PM
                for hour in range(8, 23, 2):
                    start_time = current_date.replace(hour=hour)
                    end_time = start_time + timedelta(hours=2)
                    
                    # Random status and price
                    status = random.choice([
                        TimeslotStatus.AVAILABLE,
                        TimeslotStatus.AVAILABLE,  # More available slots
                        TimeslotStatus.RESERVED,
                        TimeslotStatus.HOLDING
                    ])
                    
                    price = random.choice([3000, 3500, 4000, 4500, 5000])
                    
                    timeslot = Timeslot(
                        field_id=field.id,
                        start=start_time,
                        end=end_time,
                        price=price,
                        currency='ARS',
                        status=status
                    )
                    
                    if status == TimeslotStatus.RESERVED:
                        timeslot.reservation_code = f"RES{random.randint(1000, 9999)}"
                    
                    db.session.add(timeslot)
        
        # Service timeslots
        for i in range(14):  # 2 weeks
            current_date = base_date + timedelta(days=i)
            
            for service_key, service in services.items():
                # Create slots every hour from 9 AM to 6 PM
                for hour in range(9, 18):
                    start_time = current_date.replace(hour=hour)
                    end_time = start_time + timedelta(minutes=service.duration_min)
                    
                    # Random status
                    status = random.choice([
                        TimeslotStatus.AVAILABLE,
                        TimeslotStatus.AVAILABLE,  # More available slots
                        TimeslotStatus.RESERVED,
                        TimeslotStatus.HOLDING
                    ])
                    
                    timeslot = Timeslot(
                        service_id=service.id,
                        start=start_time,
                        end=end_time,
                        price=service.base_price,
                        currency='ARS',
                        status=status
                    )
                    
                    if status == TimeslotStatus.RESERVED:
                        timeslot.reservation_code = f"SRV{random.randint(1000, 9999)}"
                    
                    db.session.add(timeslot)
        
        db.session.commit()
        print("Database seeded successfully!")
        print(f"Created admin user: {admin_email} / admin123")
        print(f"Created manager user: {regular_admin_email} / manager123")

if __name__ == '__main__':
    seed_database()
