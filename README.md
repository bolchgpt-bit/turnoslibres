# TurnosLibres - Sistema de Gestión de Turnos

Sistema completo de gestión de turnos para tres verticales: Deportes, Estética y Profesionales.

## Características

- **Marketplace de turnos** con 3 verticales (deportes, estética, profesionales)
- **Sistema de roles** (público, admin de complejo, superadmin)
- **Waitlist inteligente** con notificaciones por email
- **Interfaz reactiva** con HTMX
- **Arquitectura escalable** con Docker y Redis
- **Seguridad robusta** con CSRF, rate limiting y validaciones

## Stack Técnico

- **Backend**: Python 3.12, Flask con app factory
- **Frontend**: Jinja2, HTMX, Tailwind CSS
- **Base de datos**: PostgreSQL con SQLAlchemy 2.x
- **Cache/Colas**: Redis con RQ (Redis Queue)
- **Autenticación**: Flask-Login
- **Deployment**: Docker + Docker Compose + Nginx

## Inicio Rápido

### Desarrollo

1. **Clonar el repositorio**
   \`\`\`bash
   git clone <repository-url>
   cd turnos-libres
   \`\`\`

2. **Configurar variables de entorno**
   \`\`\`bash
   cp .env.example .env
   # Editar .env con tus configuraciones
   \`\`\`

3. **Iniciar con Docker**
   \`\`\`bash
   make up-dev
   \`\`\`

4. **Acceder a la aplicación**
   - Aplicación: http://localhost:8000
   - MailHog (emails): http://localhost:8025
   - Admin: admin@turnoslibres.com / admin123

### Producción

1. **Configurar variables de producción**
   \`\`\`bash
   cp .env.production .env
   # Completar con valores de producción
   \`\`\`

2. **Iniciar en producción**
   \`\`\`bash
   make prod-up
   \`\`\`

## Comandos Útiles

\`\`\`bash
# Desarrollo
make up-dev          # Iniciar con MailHog
make logs            # Ver logs
make shell           # Shell en contenedor web
make migrate         # Ejecutar migraciones
make seed            # Poblar base de datos
make test-email      # Probar envío de emails

# Producción
make prod-up         # Iniciar producción
make backup-db       # Backup de base de datos
make health          # Verificar salud de servicios

# Utilidades
make clean           # Limpiar recursos Docker
make help            # Ver todos los comandos
\`\`\`

## Estructura del Proyecto

\`\`\`
turnos-libres/
├── app/
│   ├── __init__.py          # App factory
│   ├── models.py            # Modelos SQLAlchemy
│   ├── admin/               # Panel de administración
│   ├── api/                 # API endpoints
│   ├── main/                # Rutas públicas
│   ├── ui/                  # Componentes HTMX
│   ├── services/            # Lógica de negocio
│   ├── workers/             # Workers para colas
│   └── templates/           # Templates Jinja2
├── migrations/              # Migraciones Alembic
├── scripts/                 # Scripts de utilidad
├── docker-compose.yml       # Configuración Docker
├── Dockerfile              # Imagen Docker
├── requirements.txt        # Dependencias Python
└── README.md
\`\`\`

## Funcionalidades

### Público
- Explorar categorías y filtrar turnos
- Suscribirse a waitlist por turno específico o criterios
- Ver detalles de complejos

### Admin de Complejo
- Gestionar turnos de sus complejos
- Confirmar/liberar reservas
- Ver estadísticas

### Super Admin
- CRUD completo de categorías, servicios, complejos
- Gestión de usuarios y permisos
- Vincular complejos con categorías

### Sistema de Waitlist
- Notificaciones automáticas por email
- Suscripción por turno específico
- Suscripción por criterios (campo/servicio + ventana de tiempo)
- Unsubscribe fácil con token único

## Seguridad

- **CSRF Protection** en todos los formularios
- **Rate Limiting** en endpoints sensibles
- **Validación robusta** con allow-lists
- **IDOR Protection** para recursos de complejos
- **Headers de seguridad** configurados
- **Sanitización** de inputs del usuario

## Base de Datos

### Modelos Principales
- `AppUser`: Usuarios del sistema
- `Complex`: Complejos/negocios
- `Category`: Categorías (deportes, estética, profesionales)
- `Service`: Servicios ofrecidos
- `Field`: Campos/canchas deportivas
- `Timeslot`: Turnos disponibles
- `Subscription`: Suscripciones de waitlist

### Migraciones
\`\`\`bash
# Crear nueva migración
make migrate-create MESSAGE="descripción del cambio"

# Aplicar migraciones
make migrate
\`\`\`

## Email y Notificaciones

El sistema utiliza workers en background para envío de emails:

- **Desarrollo**: MailHog para testing
- **Producción**: SMTP configurable (Gmail, SendGrid, etc.)
- **Templates**: HTML responsivos con unsubscribe
- **Colas**: Redis Queue para procesamiento asíncrono

## Deployment

### Desarrollo Local
\`\`\`bash
make up-dev
\`\`\`

### Producción con Docker
\`\`\`bash
# Con Nginx reverse proxy
make prod-up
\`\`\`

### Variables de Entorno Requeridas
- `SECRET_KEY`: Clave secreta de Flask
- `DATABASE_URL`: URL de PostgreSQL
- `REDIS_URL`: URL de Redis
- `SMTP_*`: Configuración de email
- `APP_BASE_URL`: URL base de la aplicación

## Testing

\`\`\`bash
# Ejecutar tests
make test

# Probar configuración de email
make test-email EMAIL=tu@email.com
\`\`\`

## Monitoreo

- **Health checks** en todos los servicios
- **Logs centralizados** con Docker
- **Métricas** de Redis y PostgreSQL
- **Rate limiting** con Nginx

## Contribuir

1. Fork del repositorio
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más detalles.

## Soporte

Para soporte técnico o preguntas:
- Crear issue en GitHub
- Email: soporte@turnoslibres.com

---

**TurnosLibres** - Simplificando la gestión de turnos para todos.
