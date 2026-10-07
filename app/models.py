import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FileStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _now():
    return datetime.now(timezone.utc)


class GeoFile(Base):
    __tablename__ = "geo_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))  # KML | SHAPEFILE
    status: Mapped[FileStatus] = mapped_column(Enum(FileStatus), default=FileStatus.PROCESSING)
    crs: Mapped[str | None] = mapped_column(String(64))
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    features: Mapped[list["Feature"]] = relationship(back_populates="file", cascade="all, delete-orphan")


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("file_id", "idx"), Index("ix_features_file_type", "file_id", "geometry_type"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("geo_files.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    layer: Mapped[str | None] = mapped_column(String(255))
    geometry_type: Mapped[str] = mapped_column(String(32))
    geometry: Mapped[dict | None] = mapped_column(JSON)  # GeoJSON, source CRS, 2D
    crs: Mapped[str] = mapped_column(String(64))
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    measure_status: Mapped[str] = mapped_column(String(16))
    area_m2: Mapped[float | None] = mapped_column(Float)
    length_m: Mapped[float | None] = mapped_column(Float)
    perimeter_m: Mapped[float | None] = mapped_column(Float)
    projected_crs: Mapped[str | None] = mapped_column(String(32))
    geodesic_area_m2: Mapped[float | None] = mapped_column(Float)
    geodesic_length_m: Mapped[float | None] = mapped_column(Float)
    warning: Mapped[str | None] = mapped_column(Text)
    file: Mapped[GeoFile] = relationship(back_populates="features")
