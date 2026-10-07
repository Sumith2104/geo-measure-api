from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import service
from app.config import settings
from app.db import get_db
from app.geo.errors import GeoFileError
from app.models import Feature, FileStatus, GeoFile
from app.schemas import FeatureOut, FeaturesOut, FileOut, MeasurementOut, MeasurementsOut, Summary

router = APIRouter(prefix="/api/files", tags=["files"])


def _get_file(db: Session, file_id: str) -> GeoFile:
    f = db.get(GeoFile, file_id)
    if not f:
        raise HTTPException(404, {"code": "FILE_NOT_FOUND", "message": "No such file"})
    return f


def _require_completed(f: GeoFile) -> None:
    if f.status != FileStatus.COMPLETED:
        raise HTTPException(409, {"code": "FILE_NOT_READY", "message": f"File status is {f.status.value}",
                                  "error_code": f.error_code})


@router.post("/", response_model=FileOut, status_code=201)
def upload(file: UploadFile, assume_crs: str | None = Query(None, description="CRS to assume if a shapefile has no .prj"),
           db: Session = Depends(get_db)):
    name = Path(file.filename or "upload").name
    try:
        kind = service.detect_kind(name)
    except GeoFileError as e:
        raise HTTPException(422, {"code": e.code, "message": e.message})
    record = GeoFile(filename=name, file_type=kind, status=FileStatus.PROCESSING)
    db.add(record)
    db.commit()
    dest_dir = settings.storage_dir / record.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / ("source" + Path(name).suffix.lower())
    size = 0
    with open(dest, "wb") as out:  # stream with a hard cap; never hold the upload in memory
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                out.close()
                service.delete_file(db, record)
                raise HTTPException(413, {"code": "FILE_TOO_LARGE",
                                          "message": f"Max upload is {settings.max_upload_bytes} bytes"})
            out.write(chunk)
    record.size_bytes = size
    record = service.process_file(db, record, dest, assume_crs)
    if record.status == FileStatus.FAILED:
        return JSONResponse(status_code=422, content={
            "detail": {"code": record.error_code, "message": record.error_message, "file_id": record.id}})
    return record


@router.get("/", response_model=list[FileOut])
def list_files(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    q = select(GeoFile).order_by(GeoFile.created_at.desc()).limit(limit).offset(offset)
    return db.scalars(q).all()


@router.get("/{file_id}/", response_model=FileOut)
def file_info(file_id: str, db: Session = Depends(get_db)):
    return _get_file(db, file_id)


@router.get("/{file_id}/features/", response_model=FeaturesOut)
def features(file_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
             geometry_type: str | None = None, include_geometry: bool = True, db: Session = Depends(get_db)):
    f = _get_file(db, file_id)
    _require_completed(f)
    base = select(Feature).where(Feature.file_id == file_id)
    if geometry_type:
        base = base.where(Feature.geometry_type == geometry_type)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Feature.idx).limit(limit).offset(offset)).all()
    items = [FeatureOut(index=r.idx, layer=r.layer, geometry_type=r.geometry_type, crs=r.crs,
                        properties=r.properties, geometry=r.geometry if include_geometry else None) for r in rows]
    return FeaturesOut(file_id=file_id, total=total, limit=limit, offset=offset, items=items)


@router.get("/{file_id}/measurements/", response_model=MeasurementsOut)
def measurements(file_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                 geometry_type: str | None = None, include_geometry: bool = False, db: Session = Depends(get_db)):
    f = _get_file(db, file_id)
    _require_completed(f)
    base = select(Feature).where(Feature.file_id == file_id)
    if geometry_type:
        base = base.where(Feature.geometry_type == geometry_type)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Feature.idx).limit(limit).offset(offset)).all()

    agg = db.execute(select(func.coalesce(func.sum(Feature.area_m2), 0.0),
                            func.coalesce(func.sum(Feature.length_m), 0.0)).where(Feature.file_id == file_id)).one()
    by_type = dict(db.execute(select(Feature.geometry_type, func.count()).where(Feature.file_id == file_id)
                              .group_by(Feature.geometry_type)).all())
    by_status = dict(db.execute(select(Feature.measure_status, func.count()).where(Feature.file_id == file_id)
                                .group_by(Feature.measure_status)).all())
    items = [MeasurementOut(
        index=r.idx, geometry_type=r.geometry_type, status=r.measure_status, area_m2=r.area_m2,
        area_ha=r.area_m2 / 10_000 if r.area_m2 is not None else None, length_m=r.length_m,
        perimeter_m=r.perimeter_m, projected_crs=r.projected_crs, geodesic_area_m2=r.geodesic_area_m2,
        geodesic_length_m=r.geodesic_length_m, warning=r.warning,
        geometry=r.geometry if include_geometry else None) for r in rows]
    return MeasurementsOut(file_id=file_id, crs=f.crs, total=total, limit=limit, offset=offset,
                           summary=Summary(total_area_m2=agg[0], total_area_ha=agg[0] / 10_000, total_length_m=agg[1],
                                           by_geometry_type=by_type, by_status=by_status), items=items)


@router.delete("/{file_id}/", status_code=204)
def delete(file_id: str, db: Session = Depends(get_db)):
    service.delete_file(db, _get_file(db, file_id))
