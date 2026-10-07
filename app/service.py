from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import shapely
from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app.config import settings
from app.geo.errors import GeoFileError
from app.geo.measure import measure
from app.geo.reader import ParsedFile, read_kml, read_shapefile_zip
from app.models import Feature, FileStatus, GeoFile

KINDS = {".kml": "KML", ".zip": "SHAPEFILE"}


def detect_kind(filename: str) -> str:
    """Map a filename extension to a file-type key, or raise on unsupported types."""
    kind = KINDS.get(Path(filename).suffix.lower())
    if not kind:
        raise GeoFileError(
            "UNSUPPORTED_FILE_TYPE",
            "Only .kml or a .zip containing a Shapefile are accepted",
        )
    return kind


def _to_row(file_id: str, raw, crs) -> Feature:
    g = raw.geometry
    m = measure(g, crs)
    gj = mapping(shapely.force_2d(g)) if g is not None and not g.is_empty else None
    return Feature(
        file_id=file_id,
        idx=raw.index,
        layer=raw.layer,
        geometry_type=g.geom_type if g is not None else "None",
        geometry=gj,
        crs=crs.to_string(),
        properties=raw.properties,
        measure_status=m.status.value,
        area_m2=m.area_m2,
        length_m=m.length_m,
        perimeter_m=m.perimeter_m,
        projected_crs=m.projected_crs,
        geodesic_area_m2=m.geodesic_area_m2,
        geodesic_length_m=m.geodesic_length_m,
        warning=m.warning,
    )


def process_file(db: Session, record: GeoFile, path: Path, assume_crs: str | None) -> GeoFile:
    """Parse *path*, measure every feature, and persist results.

    On success the record transitions to COMPLETED; on any
    ``GeoFileError`` it transitions to FAILED with the error code.
    """
    try:
        parsed: ParsedFile = (
            read_kml(path)
            if record.file_type == "KML"
            else read_shapefile_zip(
                path,
                max_uncompressed=settings.max_zip_uncompressed_bytes,
                max_entries=settings.max_zip_entries,
                assume_crs=assume_crs,
            )
        )
        if not parsed.features:
            raise GeoFileError("NO_FEATURES", "File contains no features")
        db.add_all([_to_row(record.id, f, parsed.crs) for f in parsed.features])
        record.crs = parsed.crs.to_string()
        record.feature_count = len(parsed.features)
        record.warnings = parsed.warnings
        record.status = FileStatus.COMPLETED
    except GeoFileError as e:
        db.rollback()
        record.status, record.error_code, record.error_message = (
            FileStatus.FAILED,
            e.code,
            e.message,
        )
    record.processed_at = datetime.now(timezone.utc)
    db.add(record)
    db.commit()
    return record


def delete_file(db: Session, record: GeoFile) -> None:
    shutil.rmtree(settings.storage_dir / record.id, ignore_errors=True)
    db.delete(record)
    db.commit()
