from __future__ import annotations

import math
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

from app.geo.errors import GeoFileError

WGS84 = CRS.from_epsg(4326)
SHP_REQUIRED = {".shp", ".shx", ".dbf"}


@dataclass
class RawFeature:
    index: int
    geometry: BaseGeometry | None
    properties: dict[str, Any]
    layer: str | None = None


@dataclass
class ParsedFile:
    crs: CRS
    features: list[RawFeature] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _jsonable(v: Any) -> Any:
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return v.isoformat()
    if hasattr(v, "item"):  # numpy scalar
        return _jsonable(v.item())
    return v if isinstance(v, (str, int, float, bool)) else str(v)


def _rows(gdf: gpd.GeoDataFrame, start: int, layer: str | None) -> list[RawFeature]:
    out = []
    cols = [c for c in gdf.columns if c != gdf.geometry.name]
    for i, (_, row) in enumerate(gdf.iterrows()):
        props = {c: _jsonable(row[c]) for c in cols}
        props = {k: v for k, v in props.items() if v is not None}
        out.append(RawFeature(start + i, row.geometry, props, layer))
    return out


def safe_extract_shapefile_zip(zip_path: Path, dest: Path, max_uncompressed: int, max_entries: int) -> list[Path]:
    """Zip-slip and zip-bomb safe: only extracts known shapefile members, flattening paths."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise GeoFileError("INVALID_ZIP", "File is not a valid zip archive")
    with zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise GeoFileError("ZIP_TOO_MANY_ENTRIES", f"Archive has more than {max_entries} entries")
        if sum(i.file_size for i in infos) > max_uncompressed:
            raise GeoFileError("ZIP_TOO_LARGE", "Archive expands beyond the allowed size")
        wanted = {".shp", ".shx", ".dbf", ".prj", ".cpg"}
        for info in infos:
            name = Path(info.filename)
            if info.is_dir() or name.suffix.lower() not in wanted or name.name.startswith(("._", "__MACOSX")):
                continue
            with (
                zf.open(info) as src,
                open(dest / name.name, "wb") as dst,
            ):  # name.name drops any ../ path
                dst.write(src.read())
    shps = sorted(dest.glob("*.shp"))
    if not shps:
        raise GeoFileError("NO_SHAPEFILE", "Zip does not contain a .shp file")
    for shp in shps:
        missing = [e for e in SHP_REQUIRED if not shp.with_suffix(e).exists()]
        if missing:
            raise GeoFileError(
                "INCOMPLETE_SHAPEFILE",
                f"{shp.name} is missing {', '.join(sorted(missing))}",
            )
    return shps


def read_shapefile_zip(
    path: Path,
    *,
    max_uncompressed: int,
    max_entries: int,
    assume_crs: str | None = None,
) -> ParsedFile:
    with tempfile.TemporaryDirectory() as tmp:
        shps = safe_extract_shapefile_zip(path, Path(tmp), max_uncompressed, max_entries)
        parsed: ParsedFile | None = None
        for shp in shps:
            try:
                gdf = gpd.read_file(shp, engine="pyogrio")
            except Exception as exc:
                raise GeoFileError("UNREADABLE_SHAPEFILE", f"Could not read {shp.name}: {exc}")
            crs = gdf.crs
            if crs is None:
                if not assume_crs:
                    raise GeoFileError(
                        "MISSING_CRS",
                        f"{shp.name} has no .prj/CRS. Re-upload with a .prj or pass ?assume_crs=EPSG:xxxx",
                    )
                crs = CRS.from_user_input(assume_crs)
            if parsed is None:
                parsed = ParsedFile(crs=CRS.from_user_input(crs))
            elif CRS.from_user_input(crs) != parsed.crs:
                gdf = gdf.to_crs(parsed.crs)
                parsed.warnings.append(f"{shp.name} reprojected to {parsed.crs.to_string()} to match first layer")
            parsed.features += _rows(gdf, len(parsed.features), shp.stem)
        assert parsed is not None
        return parsed


def read_kml(path: Path) -> ParsedFile:
    try:
        layers = [str(n) for n, _ in pyogrio.list_layers(path)]  # each KML <Folder> becomes a layer
    except Exception as exc:
        raise GeoFileError("UNREADABLE_KML", f"Could not parse KML: {exc}")
    parsed = ParsedFile(crs=WGS84)  # KML is always WGS84 lon/lat
    for layer in layers:
        gdf = gpd.read_file(path, layer=layer, engine="pyogrio")
        parsed.features += _rows(gdf, len(parsed.features), layer)
    return parsed
