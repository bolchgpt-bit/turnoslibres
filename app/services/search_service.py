from sqlalchemy import select, func, text
from app import db
from app.models_catalog import Professional, BeautyCenter, SportsComplex

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 50

def _paginate(q, page: int, per_page: int):
    per_page = min(max(per_page or PAGE_SIZE_DEFAULT, 1), PAGE_SIZE_MAX)
    offset = max(page - 1, 0) * per_page
    return q.limit(per_page).offset(offset)

def _fts_clause(table_name: str):
    # plainto_tsquery + unaccent para FTS robusto
    return text(f"{table_name}.search_vector @@ plainto_tsquery('simple', unaccent(:query))")

def _order_fts(model, query: str):
    return [
        func.ts_rank_cd(model.search_vector, func.plainto_tsquery('simple', func.unaccent(query))).desc(),
        model.name.asc(),
    ]

def search_professionals(query: str = "", city: str | None = None, page: int = 1, per_page: int = 20):
    base = select(Professional).where(Professional.is_active.is_(True))
    if city:
        base = base.where(Professional.city.ilike(f"%{city}%"))
    if query and len(query.strip()) >= 2:
        base = base.where(_fts_clause("professionals")).params(query=query).order_by(*_order_fts(Professional, query))
    elif query:
        base = base.where(Professional.name.ilike(f"%{query}%")).order_by(Professional.name.asc())
    else:
        base = base.order_by(Professional.name.asc())
    q = _paginate(base, page, per_page)
    return db.session.execute(q).scalars().all()

def search_beauty_centers(query: str = "", city: str | None = None, page: int = 1, per_page: int = 20):
    base = select(BeautyCenter).where(BeautyCenter.is_active.is_(True))
    if city:
        base = base.where(BeautyCenter.city.ilike(f"%{city}%"))
    if query and len(query.strip()) >= 2:
        base = base.where(_fts_clause("beauty_centers")).params(query=query).order_by(*_order_fts(BeautyCenter, query))
    elif query:
        base = base.where(BeautyCenter.name.ilike(f"%{query}%")).order_by(BeautyCenter.name.asc())
    else:
        base = base.order_by(BeautyCenter.name.asc())
    q = _paginate(base, page, per_page)
    return db.session.execute(q).scalars().all()

def search_sports_complexes(query: str = "", city: str | None = None, page: int = 1, per_page: int = 20):
    base = select(SportsComplex).where(SportsComplex.is_active.is_(True))
    if city:
        base = base.where(SportsComplex.city.ilike(f"%{city}%"))
    if query and len(query.strip()) >= 2:
        base = base.where(_fts_clause("sports_complexes")).params(query=query).order_by(*_order_fts(SportsComplex, query))
    elif query:
        base = base.where(SportsComplex.name.ilike(f"%{query}%")).order_by(SportsComplex.name.asc())
    else:
        base = base.order_by(SportsComplex.name.asc())
    q = _paginate(base, page, per_page)
    return db.session.execute(q).scalars().all()
