import numpy as np
import pytest
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.geo.crs import pick_projected_crs, utm_epsg
from app.geo.measure import MeasureStatus, measure

WGS = CRS.from_epsg(4326)


def to_wgs(geom, epsg):
    t = Transformer.from_crs(epsg, 4326, always_xy=True)
    return shapely.transform(geom, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))


@pytest.mark.parametrize(
    "epsg,x,y",
    [(32643, 500000, 1430000), (32632, 700000, 5000000), (32755, 300000, 6000000)],
)
def test_1km_square_area_close_to_1e6(epsg, x, y):
    g = to_wgs(box(x, y, x + 1000, y + 1000), epsg)
    m = measure(g, WGS)
    assert m.status == MeasureStatus.MEASURED
    assert m.area_m2 == pytest.approx(1_000_000, rel=0.002)
    assert m.geodesic_area_m2 == pytest.approx(m.area_m2, rel=0.005)


def test_area_with_hole_and_multipolygon():
    outer = [(77.5, 12.9), (77.51, 12.9), (77.51, 12.91), (77.5, 12.91)]
    hole = [(77.503, 12.903), (77.507, 12.903), (77.507, 12.907), (77.503, 12.907)]
    solid = measure(Polygon(outer), WGS)
    holed = measure(Polygon(outer, [hole]), WGS)
    assert holed.area_m2 < solid.area_m2
    assert holed.geodesic_area_m2 == pytest.approx(holed.area_m2, rel=0.005)
    mp = measure(MultiPolygon([Polygon(outer), Polygon(outer, [hole])]), WGS)
    assert mp.area_m2 == pytest.approx(solid.area_m2 + holed.area_m2, rel=0.01)


def test_line_length_one_degree_lat_about_111km():
    m = measure(LineString([(77.5, 12.0), (77.5, 13.0)]), WGS)
    assert m.length_m == pytest.approx(110_700, rel=0.003)


def test_degrees_never_used():
    m = measure(Polygon([(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01)]), WGS)
    assert m.area_m2 > 1e6  # degrees^2 would give 0.0001


def test_point_not_applicable_collection_unsupported_empty_unsupported():
    assert measure(Point(1, 1), WGS).status == MeasureStatus.NOT_APPLICABLE
    assert measure(GeometryCollection([Point(1, 1)]), WGS).status == MeasureStatus.UNSUPPORTED
    assert measure(Polygon(), WGS).status == MeasureStatus.UNSUPPORTED
    assert measure(None, WGS).status == MeasureStatus.UNSUPPORTED


def test_3d_coordinates_ignored():
    m = measure(Polygon([(77.5, 12.9, 900), (77.51, 12.9, 900), (77.51, 12.91, 900)]), WGS)
    assert m.status == MeasureStatus.MEASURED


def test_projected_metric_source_kept():
    src = CRS.from_epsg(32643)
    m = measure(box(500000, 1430000, 501000, 1431000), src)
    assert m.area_m2 == pytest.approx(1_000_000)
    assert m.projected_crs == "EPSG:32643"


def test_non_metric_projected_reprojected():
    src = CRS.from_epsg(2263)  # NY Long Island, US survey feet
    m = measure(box(1000000, 200000, 1003280.833, 203280.833), src)  # ~1 km square
    assert m.projected_crs.startswith("EPSG:326")
    assert m.area_m2 == pytest.approx(1_000_000, rel=0.01)


def test_invalid_polygon_flagged():
    bow = Polygon([(77.5, 12.9), (77.51, 12.91), (77.51, 12.9), (77.5, 12.91)])
    assert "invalid" in measure(bow, WGS).warning


def test_zone_selection():
    assert utm_epsg(77.5, 12.9) == 32643
    assert utm_epsg(-122.4, 37.7) == 32610
    assert utm_epsg(151.2, -33.8) == 32756
    assert pick_projected_crs(Point(0, 85), WGS).to_epsg() == 3413
    assert pick_projected_crs(Point(0, -85), WGS).to_epsg() == 3031
