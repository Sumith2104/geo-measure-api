from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import shapely
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

from app.geo.crs import get_transformer, pick_projected_crs


class MeasureStatus(str, Enum):
    MEASURED = "MEASURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # points
    UNSUPPORTED = "UNSUPPORTED"  # collections, empty/null geometry
    ERROR = "ERROR"


@dataclass
class Measurement:
    status: MeasureStatus
    area_m2: float | None = None
    length_m: float | None = None  # lines only
    perimeter_m: float | None = None  # polygons only
    projected_crs: str | None = None
    geodesic_area_m2: float | None = None  # independent cross-check (geographic sources only)
    geodesic_length_m: float | None = None
    warning: str | None = None


POLY = {"Polygon", "MultiPolygon"}
LINE = {"LineString", "MultiLineString"}
POINT = {"Point", "MultiPoint"}


def _project(geom: BaseGeometry, src: CRS, dst_epsg: int) -> BaseGeometry:
    """Reproject *geom* from *src* CRS to the given EPSG using a cached Transformer."""
    t = get_transformer(src.to_wkt(), dst_epsg)
    return shapely.transform(geom, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))


def _ring_area_perimeter(geod, ring) -> tuple[float, float]:
    """Return the absolute geodesic area and perimeter of a single ring."""
    xs, ys = zip(*[(c[0], c[1]) for c in ring.coords])
    a, per = geod.polygon_area_perimeter(xs, ys)
    return abs(a), per


def _geodesic(geom: BaseGeometry, src: CRS) -> tuple[float | None, float | None]:
    """Ellipsoidal cross-check. Rings handled explicitly because Geod's polygon helper ignores holes."""
    if not src.is_geographic:
        return None, None
    geod = src.get_geod()
    area = length = 0.0
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type == "Polygon":
            a, per = _ring_area_perimeter(geod, p.exterior)
            area += a
            length += per
            for hole in p.interiors:
                ha, hper = _ring_area_perimeter(geod, hole)
                area -= ha
                length += hper
        else:
            length += geod.geometry_length(p)
    return area, length


def measure(geom: BaseGeometry | None, src: CRS) -> Measurement:
    """Compute area/length for a single geometry in metric units.

    Returns a Measurement with status indicating success or reason for
    skipping.  Never raises — errors are captured as MeasureStatus.ERROR
    so one bad feature cannot fail an entire file.
    """
    if geom is None or geom.is_empty:
        return Measurement(MeasureStatus.UNSUPPORTED, warning="null or empty geometry")
    gt = geom.geom_type
    if gt in POINT:
        return Measurement(MeasureStatus.NOT_APPLICABLE)
    if gt not in POLY | LINE:
        return Measurement(MeasureStatus.UNSUPPORTED, warning=f"{gt} is not supported for measurement")
    try:
        geom = shapely.force_2d(geom)  # KML carries altitude; we measure on the surface
        warning = None if geom.is_valid else "invalid geometry (self-intersection or similar); result may be unreliable"
        dst = pick_projected_crs(geom, src)
        projected = geom if dst == src else _project(geom, src, dst.to_epsg())
        g_area, g_len = _geodesic(geom, src)
        if gt in POLY:
            return Measurement(
                MeasureStatus.MEASURED,
                area_m2=projected.area,
                perimeter_m=projected.length,
                projected_crs=dst.to_string(),
                geodesic_area_m2=g_area,
                geodesic_length_m=g_len,
                warning=warning,
            )
        return Measurement(
            MeasureStatus.MEASURED,
            length_m=projected.length,
            projected_crs=dst.to_string(),
            geodesic_length_m=g_len,
            warning=warning,
        )
    except Exception as exc:  # one bad feature must never fail the file
        return Measurement(MeasureStatus.ERROR, warning=f"measurement failed: {exc}")
