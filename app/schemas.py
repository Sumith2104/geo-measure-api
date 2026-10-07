from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    file_type: str
    status: str
    crs: str | None
    feature_count: int
    warnings: list[str] = []
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    processed_at: datetime | None = None


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    index: int
    layer: str | None
    geometry_type: str
    crs: str
    properties: dict[str, Any]
    geometry: dict | None = None


class MeasurementOut(BaseModel):
    index: int
    geometry_type: str
    status: str
    area_m2: float | None = None
    area_ha: float | None = None
    length_m: float | None = None
    perimeter_m: float | None = None
    projected_crs: str | None = None
    geodesic_area_m2: float | None = None
    geodesic_length_m: float | None = None
    warning: str | None = None
    geometry: dict | None = None


class Summary(BaseModel):
    total_area_m2: float
    total_area_ha: float
    total_length_m: float
    by_geometry_type: dict[str, int]
    by_status: dict[str, int]


class MeasurementsOut(BaseModel):
    file_id: str
    crs: str | None
    total: int
    limit: int
    offset: int
    summary: Summary
    items: list[MeasurementOut]


class FeaturesOut(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    items: list[FeatureOut]
