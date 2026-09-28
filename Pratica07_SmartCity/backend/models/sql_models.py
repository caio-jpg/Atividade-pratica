from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class CategoryResponse(BaseModel):
    # from_attributes permite devolver objetos do SQLAlchemy diretamente
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class DashboardViewCreate(BaseModel):
    name: str
    filters: Dict[str, Any]


class DashboardViewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    filters: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
