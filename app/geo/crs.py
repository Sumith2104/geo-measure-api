"""CRS selection: never measure in degrees."""

from __future__ import annotations

from functools import lru_cache

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

WGS84 = CRS.from_epsg(4326)
NORTH_POLAR_EPSG = 3413  # NSIDC Polar Stereographic North
SOUTH_POLAR_EPSG = 3031  # Antarctic Polar Stereographic
POLAR_LAT = 80.0


def is_metric_projected(crs: CRS) -> bool:
    return bool(
        crs.is_projected and crs.axis_info and all(abs(a.unit_conversion_factor - 1.0) < 1e-9 for a in crs.axis_info)
    )


def utm_epsg(lon: float, lat: float) -> int:
    lon = ((lon + 180.0) % 360.0) - 180.0
    zone = min(int((lon + 180.0) // 6) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


@lru_cache(maxsize=256)
def get_transformer(src_wkt: str, dst_epsg: int) -> Transformer:
    return Transformer.from_crs(CRS.from_wkt(src_wkt), CRS.from_epsg(dst_epsg), always_xy=True)


def representative_lonlat(geom: BaseGeometry, src: CRS) -> tuple[float, float]:
    p = geom.representative_point()  # always inside the geometry, unlike centroid
    if src.is_geographic:
        return p.x, p.y
    t = Transformer.from_crs(src, WGS84, always_xy=True)
    return t.transform(p.x, p.y)


def pick_projected_crs(geom: BaseGeometry, src: CRS) -> CRS:
    """Metric projected source CRS is kept; otherwise polar or UTM zone of the feature."""
    if is_metric_projected(src):
        return src
    lon, lat = representative_lonlat(geom, src)
    if lat >= POLAR_LAT:
        return CRS.from_epsg(NORTH_POLAR_EPSG)
    if lat <= -POLAR_LAT:
        return CRS.from_epsg(SOUTH_POLAR_EPSG)
    return CRS.from_epsg(utm_epsg(lon, lat))
