from flask import Blueprint, request, render_template
from app.services.search_service import (
    search_professionals, search_beauty_centers, search_sports_complexes
)

search_bp = Blueprint("search", __name__, url_prefix="/buscar")

@search_bp.get("/profesionales")
def profesionales():
    q = request.args.get("q", "", type=str)
    city = request.args.get("city", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    results = search_professionals(q, city, page, per_page)
    return render_template("search/profesionales.html", results=results, q=q, city=city, page=page)

@search_bp.get("/centros-estetica")
def centros():
    q = request.args.get("q", "", type=str)
    city = request.args.get("city", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    results = search_beauty_centers(q, city, page, per_page)
    return render_template("search/centros.html", results=results, q=q, city=city, page=page)

@search_bp.get("/complejos-deportivos")
def complejos():
    q = request.args.get("q", "", type=str)
    city = request.args.get("city", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    results = search_sports_complexes(q, city, page, per_page)
    return render_template("search/complejos.html", results=results, q=q, city=city, page=page)
