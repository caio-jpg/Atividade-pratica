from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GeometryType(str, Enum):
    POINT = "Point"
    LINESTRING = "LineString"
    POLYGON = "Polygon"
    MULTIPOINT = "MultiPoint"
    MULTILINESTRING = "MultiLineString"
    MULTIPOLYGON = "MultiPolygon"


class Geometry(BaseModel):
    type: GeometryType
    coordinates: List[Any]


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: Geometry
    properties: Dict[str, Any]


class SpatialDataCreate(BaseModel):
    name: str
    category: str
    geometry: Geometry
    properties: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class SpatialDataResponse(BaseModel):
    id: str
    name: str
    category: str
    geometry: Geometry
    properties: Dict[str, Any]
    timestamp: Optional[datetime] = None
    distance_m: Optional[float] = None


class GeospatialQuery(BaseModel):
    query_type: Optional[str] = None  # near | within | intersects | None (só filtros)
    geometry: Optional[Geometry] = None
    coordinates: Optional[List[float]] = None  # [lon, lat] para "near"
    max_distance: Optional[float] = None  # metros
    category: Optional[str] = None
    categories: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 1000


# ---------------------------------------------------------------------------
# Restaurantes (collection "restaurantes", importada de restaurantes.json)
# ---------------------------------------------------------------------------
class RestaurantResponse(BaseModel):
    id: str
    title: str
    type: List[str] = []
    rating: Optional[float] = None
    reviewsCount: Optional[int] = None
    deliveryFee: Optional[float] = None
    minCharge: Optional[str] = None
    isOpen: Optional[bool] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    neighborhood: Optional[str] = None
    street: Optional[str] = None
    coordinates: List[float]  # [lon, lat]
    distance_km: Optional[float] = None
