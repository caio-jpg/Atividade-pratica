"""
Rotas da API (prefixo /api/v1).

Observação: as rotas são funções síncronas (`def`) porque o PyMongo e o
SQLAlchemy são bloqueantes — o FastAPI as executa num pool de threads.
"""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from backend.db.mongodb import mongo_conn
from backend.db.sqlite import AuditLog, Category, DashboardView, sqlite_conn
from backend.models.geo_models import (
    GeospatialQuery,
    RestaurantResponse,
    SpatialDataCreate,
    SpatialDataResponse,
)
from backend.models.sql_models import (
    CategoryCreate,
    CategoryResponse,
    DashboardViewCreate,
    DashboardViewResponse,
)

router = APIRouter()
SPATIAL = "spatial_data"
RESTAURANTES = "restaurantes"
RAIO_TERRA_KM = 6378.1


def _doc_to_response(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "category": doc["category"],
        "geometry": doc["geometry"],
        "properties": doc.get("properties", {}),
        "timestamp": doc.get("timestamp"),
        "distance_m": round(doc["distance_m"], 1) if "distance_m" in doc else None,
    }


# ==================== MONGODB — DADOS GEOESPACIAIS ====================

@router.post("/spatial-data", response_model=SpatialDataResponse)
def create_spatial_data(data: SpatialDataCreate):
    """Inserir novo dado geoespacial (GeoJSON) no MongoDB."""
    try:
        document = {
            "name": data.name,
            "category": data.category,
            "geometry": data.geometry.model_dump(mode="json"),
            "properties": data.properties,
            "timestamp": data.timestamp or datetime.utcnow(),
            "created_at": datetime.utcnow(),
        }
        result = mongo_conn.get_collection(SPATIAL).insert_one(document)
        log_audit("CREATE_SPATIAL", {"id": str(result.inserted_id), "name": data.name})
        document["_id"] = result.inserted_id
        return _doc_to_response(document)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spatial-data", response_model=List[SpatialDataResponse])
def get_spatial_data(category: Optional[str] = None, limit: int = 1000):
    """Consultar dados geoespaciais (filtro simples por categoria)."""
    try:
        query = {"category": category} if category else {}
        return [_doc_to_response(d) for d in mongo_conn.get_collection(SPATIAL).find(query).limit(limit)]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spatial-data/{item_id}", response_model=SpatialDataResponse)
def get_spatial_item(item_id: str):
    try:
        doc = mongo_conn.get_collection(SPATIAL).find_one({"_id": ObjectId(item_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="id inválido")
    if not doc:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return _doc_to_response(doc)


@router.delete("/spatial-data/{item_id}")
def delete_spatial_item(item_id: str):
    try:
        res = mongo_conn.get_collection(SPATIAL).delete_one({"_id": ObjectId(item_id)})
    except InvalidId:
        raise HTTPException(status_code=400, detail="id inválido")
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    log_audit("DELETE_SPATIAL", {"id": item_id})
    return {"message": "Item removido"}


@router.post("/spatial-data/query", response_model=List[SpatialDataResponse])
def query_spatial_data(query: GeospatialQuery):
    """
    Consulta combinada: categorias + intervalo de datas + operador geoespacial.
      - near       : pontos/polígonos até `max_distance` metros de `coordinates` ([lon, lat]),
                     ordenados por distância e com o campo distance_m ($geoNear)
      - within     : geometrias totalmente dentro de `geometry` ($geoWithin)
      - intersects : geometrias que cruzam `geometry` ($geoIntersects)
    """
    try:
        collection = mongo_conn.get_collection(SPATIAL)
        filtro = {}

        categorias = query.categories or ([query.category] if query.category else [])
        if categorias:
            filtro["category"] = {"$in": categorias}

        if query.date_from or query.date_to:
            filtro["timestamp"] = {}
            if query.date_from:
                filtro["timestamp"]["$gte"] = query.date_from
            if query.date_to:
                filtro["timestamp"]["$lte"] = query.date_to

        if query.query_type == "near":
            if not query.coordinates:
                raise HTTPException(status_code=422, detail="'near' exige coordinates [lon, lat]")
            pipeline = [
                {"$geoNear": {
                    "near": {"type": "Point", "coordinates": query.coordinates},
                    "distanceField": "distance_m",
                    "maxDistance": query.max_distance or 1000,
                    "query": filtro,
                    "spherical": True,
                }},
                {"$limit": query.limit},
            ]
            docs = list(collection.aggregate(pipeline))
        else:
            if query.query_type in ("within", "intersects"):
                if not query.geometry:
                    raise HTTPException(status_code=422, detail=f"'{query.query_type}' exige geometry")
                op = "$geoWithin" if query.query_type == "within" else "$geoIntersects"
                filtro["geometry"] = {op: {"$geometry": query.geometry.model_dump(mode="json")}}
            docs = list(collection.find(filtro).limit(query.limit))

        log_audit("QUERY_SPATIAL", {"type": query.query_type, "categories": categorias, "count": len(docs)})
        return [_doc_to_response(d) for d in docs]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/aggregated")
def get_aggregated_analytics():
    """Dados agregados para gráficos (contagem por categoria e por mês)."""
    try:
        collection = mongo_conn.get_collection(SPATIAL)
        category_counts = collection.aggregate([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        temporal_data = collection.aggregate([
            {"$match": {"timestamp": {"$type": "date"}}},
            {"$group": {
                "_id": {"year": {"$year": "$timestamp"}, "month": {"$month": "$timestamp"}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ])
        return {"category_counts": list(category_counts), "temporal_data": list(temporal_data)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MONGODB — RESTAURANTES ====================

def _rest_to_response(doc: dict) -> dict:
    addr = doc.get("address", {}) or {}
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title"),
        "type": doc.get("type", []),
        "rating": doc.get("rating"),
        "reviewsCount": doc.get("reviewsCount"),
        "deliveryFee": doc.get("deliveryFee"),
        "minCharge": doc.get("minCharge"),
        "isOpen": doc.get("isOpen"),
        "phone": doc.get("phone"),
        "city": addr.get("city"),
        "state": addr.get("state"),
        "neighborhood": addr.get("neighborhood"),
        "street": addr.get("street"),
        "coordinates": addr.get("location", {}).get("coordinates", []),
        "distance_km": round(doc["dist_m"] / 1000, 2) if "dist_m" in doc else None,
    }


def _rest_filters(tipo, aberto, rating_min, estado) -> dict:
    f = {}
    if tipo:
        f["type"] = tipo
    if aberto is not None:
        f["isOpen"] = aberto
    if rating_min is not None:
        f["rating"] = {"$gte": rating_min}
    if estado:
        f["address.state"] = estado.upper()
    return f


@router.get("/restaurantes/near", response_model=List[RestaurantResponse])
def restaurantes_proximos(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    max_km: float = Query(50, gt=0),
    tipo: Optional[str] = None,
    aberto: Optional[bool] = None,
    rating_min: Optional[float] = None,
    limit: int = Query(50, le=500),
):
    """Restaurantes mais próximos de um ponto ($geoNear), com a distância em km."""
    try:
        pipeline = [
            {"$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "dist_m",
                "maxDistance": max_km * 1000,
                "query": _rest_filters(tipo, aberto, rating_min, None),
                "spherical": True,
            }},
            {"$limit": limit},
        ]
        docs = list(mongo_conn.get_collection(RESTAURANTES).aggregate(pipeline))
        log_audit("QUERY_RESTAURANTES_NEAR", {"lon": lon, "lat": lat, "max_km": max_km, "count": len(docs)})
        return [_rest_to_response(d) for d in docs]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/restaurantes/raio")
def restaurantes_no_raio(lon: float, lat: float, raio_km: float = 100):
    """Quantidade de restaurantes num círculo ($geoWithin + $centerSphere)."""
    total = mongo_conn.get_collection(RESTAURANTES).count_documents({
        "address.location": {"$geoWithin": {"$centerSphere": [[lon, lat], raio_km / RAIO_TERRA_KM]}}
    })
    return {"lon": lon, "lat": lat, "raio_km": raio_km, "total": total}


@router.get("/restaurantes", response_model=List[RestaurantResponse])
def listar_restaurantes(
    tipo: Optional[str] = None,
    aberto: Optional[bool] = None,
    rating_min: Optional[float] = None,
    estado: Optional[str] = None,
    limit: int = Query(100, le=5000),
):
    """Lista restaurantes com filtros, ordenados pela nota (maior primeiro)."""
    cursor = (mongo_conn.get_collection(RESTAURANTES)
              .find(_rest_filters(tipo, aberto, rating_min, estado))
              .sort("rating", -1).limit(limit))
    return [_rest_to_response(d) for d in cursor]


@router.get("/restaurantes/stats")
def estatisticas_restaurantes():
    """Agregações: por tipo de cozinha, por estado e abertos x fechados."""
    col = mongo_conn.get_collection(RESTAURANTES)
    por_tipo = list(col.aggregate([
        {"$unwind": "$type"},
        {"$group": {"_id": "$type", "total": {"$sum": 1}, "rating_medio": {"$avg": "$rating"},
                    "taxa_media": {"$avg": "$deliveryFee"}}},
        {"$sort": {"total": -1}},
    ]))
    por_estado = list(col.aggregate([
        {"$group": {"_id": "$address.state", "total": {"$sum": 1}, "rating_medio": {"$avg": "$rating"}}},
        {"$sort": {"total": -1}},
    ]))
    abertos = list(col.aggregate([{"$group": {"_id": "$isOpen", "total": {"$sum": 1}}}]))
    return {
        "total": col.count_documents({}),
        "por_tipo": por_tipo,
        "por_estado": por_estado,
        "abertos": {str(a["_id"]).lower(): a["total"] for a in abertos},
    }


# ==================== SQLITE ROUTES ====================

@router.post("/categories", response_model=CategoryResponse)
def create_category(category: CategoryCreate):
    """Criar nova categoria."""
    try:
        with sqlite_conn.session_scope() as session:
            db_category = Category(**category.model_dump())
            session.add(db_category)
            session.flush()
            result = CategoryResponse.model_validate(db_category)
        log_audit("CREATE_CATEGORY", {"name": category.name})
        return result
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Categoria já existe")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories", response_model=List[CategoryResponse])
def get_categories():
    """Listar todas as categorias."""
    with sqlite_conn.session_scope() as session:
        return [CategoryResponse.model_validate(c) for c in session.query(Category).order_by(Category.name)]


@router.post("/dashboard-views", response_model=DashboardViewResponse)
def save_dashboard_view(view: DashboardViewCreate):
    """Salvar configuração (filtros) de visualização do dashboard."""
    try:
        with sqlite_conn.session_scope() as session:
            db_view = DashboardView(name=view.name, filters=view.filters)
            session.add(db_view)
            session.flush()
            result = DashboardViewResponse.model_validate(db_view)
        log_audit("SAVE_VIEW", {"name": view.name})
        return result
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard-views", response_model=List[DashboardViewResponse])
def get_dashboard_views():
    """Listar visualizações salvas (mais recente primeiro)."""
    with sqlite_conn.session_scope() as session:
        views = session.query(DashboardView).order_by(DashboardView.created_at.desc()).all()
        return [DashboardViewResponse.model_validate(v) for v in views]


@router.delete("/dashboard-views/{view_id}")
def delete_dashboard_view(view_id: int):
    """Deletar visualização salva."""
    with sqlite_conn.session_scope() as session:
        view = session.query(DashboardView).filter(DashboardView.id == view_id).first()
        if not view:
            raise HTTPException(status_code=404, detail="View não encontrada")
        session.delete(view)
    log_audit("DELETE_VIEW", {"id": view_id})
    return {"message": "View deletada com sucesso"}


@router.get("/audit-logs")
def get_audit_logs(limit: int = 50):
    """Últimas ações registradas no log de auditoria."""
    with sqlite_conn.session_scope() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
        return [{"id": l.id, "action": l.action, "details": l.details, "timestamp": l.timestamp} for l in logs]


# ==================== HELPER FUNCTIONS ====================

def log_audit(action: str, details: dict):
    """Registrar ação no log de auditoria (SQLite)."""
    try:
        with sqlite_conn.session_scope() as session:
            session.add(AuditLog(action=action, details=details))
    except Exception as e:  # noqa: BLE001
        print(f"Erro ao registrar log: {e}")
