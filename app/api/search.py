from flask import Blueprint, request, jsonify
from app.services.search_service import (
    search_professionals, search_beauty_centers, search_sports_complexes
)

api_search = Blueprint("api_search", __name__, url_prefix="/api/v1/search")

@api_search.get("/professionals")
def api_professionals():
    q = request.args.get("q", "", type=str)
    city = request.args.get("city", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items = search_professionals(q, city, page, per_page)
    return jsonify([{ "id": r.id, "name": r.name, "slug": r.slug, "city": r.city, "specialties": r.specialties } for r in items])

@api_search.get("/beauty-centers")
def api_beauty_centers():
    q = request.args.get("q", "", type=str)
    city = request.args.get("city", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items = search_beauty_centers(q, city, page, per_page)
    return jsonify([{ "id": r.id, "name": r.name, "slug": r.slug, "city": r.city, "services": r.services } for r in items])

@api_search.get("/sports-complexes")
def api_sports_complexes():
    q = request.args.get("q", "", type=str)
    city = request.args.get("city", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items = search_sports_complexes(q, city, page, per_page)
    return jsonify([{ "id": r.id, "name": r.name, "slug": r.slug, "city": r.city, "sports": r.sports } for r in items])
