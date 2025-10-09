from flask import Blueprint

bp = Blueprint('api', __name__)

# Cargar rutas reales del API (routes.py en UTF-8)
from app.api import routes  # noqa: F401

