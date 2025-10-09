# 🤖 Agents Guide — TurnosLibres

## Ambito y precedencia
- Este AGENTS.md aplica a todo el repositorio. Cualquier AGENTS.md en subdirectorios puede sobrescribir instrucciones dentro de su propio arbol.
- Las instrucciones directas del usuario en Codex siempre tienen prioridad.

## 1. Contexto General del Proyecto

**TurnosLibres** es una plataforma modular para la gestión de turnos en múltiples verticales:
- **Deportes:** canchas de fútbol, pádel, tenis, etc.
- **Estética y Profesionales:** peluquerías, barberías, centros médicos, etc.

### Stack principal
- **Backend:** Flask (App Factory Pattern + Blueprints)
- **Base de datos:** PostgreSQL
- **ORM:** SQLAlchemy 2.x con declaraciones tipo 2.0
- **Frontend:** Jinja + HTMX + TailwindCSS
- **Asincronía:** Redis + RQ
- **Autenticación:** Flask-Login + Flask-WTF + CSRFProtect
- **Infraestructura:** Docker Compose (dev/prod)
- **Entorno de desarrollo:** VS Code + Codex + GitHub

---

**Reglas de estructura**
- No crear rutas o vistas fuera de los Blueprints existentes.
- No modificar `create_app()` en `app/__init__.py` salvo para inicializar extensiones o registrar Blueprints.
- No introducir frameworks externos de frontend (React, Vue, etc.).
- Mantener todos los recursos estáticos dentro de `app/static/`.

---

## 3. Convenciones de Código

### Python
- Cumplir **PEP8** + formateo **Black**.
- Nombres en **snake_case**.
- Un modelo por archivo dentro de `models/`.
- Evitar lógica en plantillas; delegarla al backend.
- Usar typing (`-> None`, `list[str]`, etc.) siempre que sea posible.

### Templates Jinja2
- Indentación de 2 espacios.
- Reutilizar bloques con `{% include %}` o `{% extends %}`.
- Respetar convención HTMX (`hx-get`, `hx-target`, `hx-swap`).
- Componentes reutilizables: `_turnos_table.html`, `_turnos_table_grouped.html`, `_modal.html`, etc.

### Frontend
- TailwindCSS compilado a `app/static/css/output.css`.
- No escribir CSS en línea.
- Mantener consistencia visual entre vistas diarias y semanales.
- No incluir dependencias JS innecesarias.

---

## 4. Seguridad y Buenas Prácticas

- Todas las vistas que modifican estado deben requerir **CSRF token**.
- Validar usuarios con `@login_required` y roles (`current_user.role`).
- No exponer IDs reales en URLs → usar UUIDs o claves hash si aplica.
- Evitar consultas SQL sin ORM.
- No imprimir datos sin `escape()`.
- Las credenciales deben leerse solo desde `.env` o variables de entorno.
- Revisar `Dockerfile` y `requirements.txt` antes de agregar paquetes externos.

---

## 5. Tareas permitidas para los agentes

✅ Refactorizar vistas, formularios y templates.
✅ Agregar tests unitarios y de integración.
✅ Mejorar rendimiento de consultas SQLAlchemy.
✅ Crear seeds o fixtures consistentes para `flask seed`.
✅ Ajustar componentes HTMX respetando comportamiento actual.
✅ Mejorar mensajes de feedback al usuario (`alert-success`, `alert-danger`).
✅ Documentar funciones y Blueprints.

---

## 6. Tareas prohibidas para los agentes

❌ Cambiar rutas o endpoints existentes sin mantener compatibilidad.
❌ Eliminar validaciones o protecciones CSRF/Login.
❌ Agregar dependencias externas no aprobadas (frameworks, librerías JS).
❌ Alterar la estructura base del App Factory o Makefile.
❌ Subir archivos `.env`, secretos o credenciales.

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
```

---

## 8. Contexto y Rendimiento para Codex

Para mantener a Codex ágil y evitar bloqueos al cargar contexto del repo:

- Áreas de foco del contexto: `app/`, `migrations/`, `tests/`, `Makefile`, `docker-compose*.yml`,
  `requirements.txt`, `tailwind.config.js`, `app.py`, `worker.py`.
- Evitar leer/minimizar en contexto: binarios/minificados, archivos gigantes o generados.
  Usar estos patrones mentales al explorar:
  - Ignorar directorios: `.git/`, `.venv/`, `venv/`, `env/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`,
    `.ruff_cache/`, `.nox/`, `node_modules/`, `dist/`, `build/`, `coverage/`, `site/`.
  - Ignorar estáticos compilados/vendor: `app/static/css/output.css`, `app/static/js/*.min.js`,
    `app/static/vendor/`, `app/static/**/dist/`.
  - Ignorar artefactos/datos: `*.sql`, `*.csv`, `*.zip`, `*.tar*`, `*.log`, `backup_*.sql`, `data/`, `uploads/`,
    `assets/`.

### Búsqueda/lectura eficiente (CLI)
- Preferir `rg` para buscar: es mucho más rápido que `grep`.
- Leer archivos en bloques cortos (≤ 250 líneas) y acotar por rutas relevantes.
- Ejemplos útiles:

```bash
# listar archivos relevantes del proyecto (excluyendo peso)
rg --files --hidden -g '!{.git,venv,.venv,env,node_modules,dist,build,coverage,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache}/**'

# buscar por rutas/funciones clave
rg -n "create_app\(|Blueprint|@login_required|CSRFProtect|SQLAlchemy" app -S --glob '!app/static/**'

# revisar solo migrations/versions de interés
rg -n "op.create_table|op.add_column" migrations/versions
```

### Prácticas para evitar bloqueos
- No abrir archivos minificados/compilados completos (CSS/JS grandes) a menos que sea imprescindible.
- No listar el árbol completo del repo si no es necesario; filtrar por `app/**` y `tests/**` primero.
- Agrupar lecturas/búsquedas por tema (evitar muchos llamados triviales sueltos).
- Si el repo se movió de carpeta, preferir rutas relativas en scripts/config.

### Estructura tras mover el repo
- Evitar rutas absolutas en `docker-compose*.yml`, `.vscode/*`, scripts y seeds.
- Montajes de volúmenes deben ser relativos al proyecto (ya configurado así).

---

## 9. Notas específicas del proyecto
- Mantener `create_app()` solo para: config, inicializar extensiones, registrar Blueprints.
- Respetar protección CSRF en toda vista que muta estado.
- No exponer IDs reales: preferir UUID/short-hash en URLs públicas.
- Mantener consistencia visual entre vistas diaria/semanal (HTMX + Tailwind).
