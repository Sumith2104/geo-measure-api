import os, zipfile
import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, box

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DATABASE_URL", f"sqlite:///{tmp_path/'t.db'}")
    monkeypatch.setenv("GEO_STORAGE_DIR", str(tmp_path / "up"))
    import importlib, app.config, app.db, app.models, app.service, app.api, app.main
    for m in (app.config, app.db, app.models, app.service, app.api, app.main):
        importlib.reload(m)
    with TestClient(app.main.create_app()) as c:
        yield c

KML = """<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>field</name><Polygon><outerBoundaryIs><LinearRing><coordinates>77.5,12.9,0 77.51,12.9,0 77.51,12.91,0 77.5,12.91,0 77.5,12.9,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>road</name><LineString><coordinates>77.5,12.9,0 77.51,12.9,0</coordinates></LineString></Placemark>
<Placemark><name>well</name><Point><coordinates>77.5,12.9,0</coordinates></Point></Placemark>
</Document></kml>"""

@pytest.fixture()
def kml_bytes(): return KML.encode()

@pytest.fixture()
def shp_zip(tmp_path):
    d = tmp_path / "s"; d.mkdir()
    gpd.GeoDataFrame({"name": ["a", "b"]}, geometry=[box(77.5, 12.9, 77.51, 12.91), box(77.52, 12.9, 77.53, 12.91)], crs="EPSG:4326").to_file(d / "f.shp")
    z = tmp_path / "f.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in d.iterdir(): zf.write(f, f.name)
    return z.read_bytes()
