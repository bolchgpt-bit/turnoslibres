import os
import re
import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

# Alembic Config object: acceso a .ini
config = context.config

# Configura logging desde alembic.ini (si existe)
if config.config_file_name and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Metadata objetivo (Flask-Migrate)
target_metadata = current_app.extensions["migrate"].db.metadata


def get_engine():
    """Obtiene el engine desde la extensión de Flask-Migrate."""

    try:
        return current_app.extensions["migrate"].db.get_engine()
    except AttributeError:
        # Compatibilidad con versiones anteriores
        return current_app.extensions["migrate"].db.engine


def get_url() -> str:
    """Devuelve la URL de la BD, escapando % para Alembic."""
    return str(get_engine().url).replace("%", "%%")


def _assert_revision_lengths(max_len: int = 32) -> None:
    """
    Valida que TODOS los scripts en migrations/versions cumplan:
      - len(revision)      <= max_len
      - len(down_revision) <= max_len (si aplica)

    Falla rápido con un mensaje claro si alguna revisión excede el límite.
    """

    base_dir = os.path.dirname(__file__)
    versions_dir = os.path.join(base_dir, "versions")

    if not os.path.isdir(versions_dir):
        # No hay carpeta de versiones, no hay nada que validar
        return

    # OJO: el grupo 2 debe capturar 1+ caracteres -> [^'"]+
    pat = re.compile(
        r'^\s*(revision|down_revision)\s*=\s*[\'"]([^\'"]+)[\'"]\s*$',
        re.IGNORECASE,
    )

    violations: list[str] = []

    for fname in os.listdir(versions_dir):
        if not fname.endswith(".py"):
            continue

        fpath = os.path.join(versions_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    m = pat.match(line)
                    if not m:
                        continue

                    key, value = m.group(1), m.group(2)

                    # down_revision = None es válido
                    if value.lower() == "none":
                        continue

                    if len(value) > max_len:
                        violations.append(
                            f"{fname}:{lineno} {key}={value} (len={len(value)})"
                        )
        except OSError as exc:
            violations.append(f"{fname}: error leyendo archivo: {exc}")

    if violations:
        details = "; ".join(violations)
        raise RuntimeError(
            f"Alembic revision id length > {max_len}: {details}"
        )


def process_revision_directives(context, revision, directives) -> None:
    """
    Hook de Alembic para:
      - Omitir migraciones vacías cuando se usa --autogenerate.
      - Validar longitud de rev_id generada.
    """

    if not getattr(config.cmd_opts, "autogenerate", False):
        return

    if not directives:
        return

    script = directives[0]

    # 1) Evitar migraciones vacías
    if script.upgrade_ops.is_empty():
        directives[:] = []
        logger.info("No changes in schema detected.")
        return

    # 2) Validar longitud de la revision generada
    if script.rev_id and len(script.rev_id) > 32:
        raise RuntimeError(
            f"Generated revision id too long ({len(script.rev_id)}): {script.rev_id}"
        )


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo 'offline'."""

    _assert_revision_lengths()

    # En modo offline Alembic usa la URL directamente
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta migraciones en modo 'online'."""

    _assert_revision_lengths()

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
            **current_app.extensions["migrate"].configure_args,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
