# 🤖 Agents Guide — TurnosLibres
> **TL;DR (resumen operativo)**
> - Cambios por módulo y en lotes pequeños.
> - Seguí §3 (Convenciones), §4 (Seguridad) y §7 (Docker) estrictamente.
> - **Salida obligatoria:** *PR diff* autocontenido (parches listos para aplicar).
> - No toques estáticos compilados ni `create_app()` salvo registro/initialización.
> - Si el alcance excede, proponé plan por pasos y pedí confirmación.

## Ámbito y precedencia
- Este AGENTS.md aplica a todo el repositorio. Cualquier AGENTS.md en subdirectorios puede sobrescribir instrucciones dentro de su propio árbol.
- Las instrucciones directas del usuario en Codex siempre tienen prioridad.

## 1. Contexto General del Proyecto
**TurnosLibres** es una plataforma modular para la gestión de turnos en múltiples verticales:
- **Deportes:** canchas de fútbol, pádel, tenis, etc.
- **Estética y Profesionales:** peluquerías, barberías, centros médicos, etc.

### Stack principal
- **Backend:** Flask (App Factory Pattern + Blueprints)
- **Base de datos:** PostgreSQL
- **ORM:** SQLAlchemy 2.x (estilo 2.0)
- **Frontend:** Jinja2 + HTMX + TailwindCSS
- **Asincronía:** Redis + RQ
- **Autenticación:** Flask-Login + Flask-WTF + CSRFProtect
- **Infraestructura:** Docker Compose (dev/prod)
- **Entorno de desarrollo:** VS Code + Codex + GitHub

---

**Reglas de estructura**
- No crear rutas o vistas fuera de los Blueprints existentes.
- No modificar `create_app()` en `app/__init__.py` salvo para inicializar extensiones o registrar Blueprints.
- No introducir frameworks externos de frontend (React, Vue, etc.).
- Mantener recursos estáticos dentro de `app/static/` (compilados por Tailwind).

---

## 3. Convenciones de Código

### Python
- Cumplir **PEP8** + formateo **Black**.
- Nombres en **snake_case**.
- Un modelo por archivo dentro de `models/` (o módulos claros).
- Evitar lógica en plantillas; delegarla a servicios/blueprints.
- Usar typing (`-> None`, `list[str]`, etc.) cuando aplique.
- SQLAlchemy 2.x: `select()`, `session.execute()`, sin API legacy `.query`.

### Templates Jinja2
- Indentación de 2 espacios.
- Reutilizar bloques con `{% include %}` / `{% extends %}`.
- Respetar convención HTMX (`hx-get`, `hx-target`, `hx-swap`).
- Mantener consistencia visual entre vistas diaria y semanal.

### Frontend
- TailwindCSS compilado a `app/static/css/output.css`.
- No escribir CSS inline. Preferir utilidades Tailwind.
- Evitar dependencias JS innecesarias.

**Salida esperada (siempre)**
- Entregar **diffs** de los archivos cambiados (bloques `diff`/`patch` listos para aplicar).
- Mantener imports ordenados, tipado cuando aplique y test mínimo si agrega lógica.
- Explicar en **3–5 bullets** qué cambiaste y por qué (sin repetir el diff).

---

## 4. Seguridad y Buenas Prácticas
- Todas las vistas que modifican estado deben requerir **CSRF token**.
- Validar usuarios con `@login_required` y roles (`current_user.role`).
- Evitar **IDOR**: filtrar por ownership/tenant al consultar/actualizar.
- No exponer IDs reales en URLs públicas → preferir UUID/slug/short-hash.
- Evitar SQL crudo; usar ORM.
- Escapar output (`markupsafe.escape`) y validar entrada.
- Variables sensibles desde `.env`/entorno; no hardcodear secretos.
- Revisar `Dockerfile` y `requirements.txt` antes de agregar paquetes.

---

## 5. Tareas permitidas para los agentes
✅ Refactorizar vistas, formularios y templates.  
✅ Agregar tests unitarios y de integración.  
✅ Mejorar rendimiento de consultas SQLAlchemy.  
✅ Crear seeds/fixtures consistentes para desarrollo.  
✅ Ajustar componentes HTMX respetando comportamiento actual.  
✅ Mejorar feedback al usuario (`alert-success`, `alert-danger`).  
✅ Documentar funciones y Blueprints.

---

## 6. Tareas prohibidas para los agentes
❌ Cambiar rutas o endpoints existentes sin mantener compatibilidad.  
❌ Eliminar validaciones o protecciones CSRF/Login.  
❌ Agregar dependencias externas no aprobadas (frameworks, librerías JS).  
❌ Alterar la estructura base del App Factory o Makefile.  
❌ Subir `.env`, secretos o credenciales.

---

## 7. Workflow de desarrollo

**Comandos principales**
```bash
# levantar entorno de desarrollo
make up-dev

# aplicar migraciones
make migrate && make upgrade

# compilar TailwindCSS
make css-dev

# ejecutar tests
pytest -v

# revisar logs
make logs
