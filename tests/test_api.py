import pytest


def up(client, name, data, **kw):
    return client.post("/api/files/", files={"file": (name, data)}, **kw)


def test_kml_flow(client, kml_bytes):
    r = up(client, "survey.kml", kml_bytes)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "COMPLETED" and body["feature_count"] == 3 and body["crs"] == "EPSG:4326"
    fid = body["id"]
    assert client.get(f"/api/files/{fid}/").json()["filename"] == "survey.kml"
    m = client.get(f"/api/files/{fid}/measurements/").json()
    types = {i["geometry_type"]: i for i in m["items"]}
    assert types["Polygon"]["area_m2"] == pytest.approx(1_200_000, rel=0.01)
    assert types["Polygon"]["projected_crs"] == "EPSG:32643"
    assert types["LineString"]["length_m"] == pytest.approx(1085, rel=0.01)
    assert types["Point"]["status"] == "NOT_APPLICABLE" and types["Point"]["area_m2"] is None
    assert m["summary"]["by_geometry_type"] == {
        "Point": 1,
        "LineString": 1,
        "Polygon": 1,
    }
    assert m["summary"]["total_area_ha"] == pytest.approx(m["summary"]["total_area_m2"] / 1e4)


def test_shapefile_flow_and_filter_pagination(client, shp_zip):
    fid = up(client, "f.zip", shp_zip).json()["id"]
    m = client.get(f"/api/files/{fid}/measurements/?limit=1&offset=1&geometry_type=Polygon").json()
    assert m["total"] == 2 and len(m["items"]) == 1 and m["items"][0]["index"] == 1
    feats = client.get(f"/api/files/{fid}/features/").json()
    assert feats["items"][0]["properties"]["name"] == "a" and feats["items"][0]["geometry"]["type"] == "Polygon"


def test_rejects_bad_extension(client):
    r = up(client, "x.txt", b"hi")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_garbage_kml_fails_cleanly_and_is_recorded(client):
    r = up(client, "bad.kml", b"not xml at all")
    assert r.status_code == 422
    fid = r.json()["detail"]["file_id"]
    assert client.get(f"/api/files/{fid}/").json()["status"] == "FAILED"
    assert client.get(f"/api/files/{fid}/measurements/").status_code == 409


def test_unknown_id_404(client):
    assert client.get("/api/files/nope/").status_code == 404


def test_delete(client, kml_bytes):
    fid = up(client, "s.kml", kml_bytes).json()["id"]
    assert client.delete(f"/api/files/{fid}/").status_code == 204
    assert client.get(f"/api/files/{fid}/").status_code == 404


def test_too_large(client, monkeypatch, kml_bytes):
    from app import api

    monkeypatch.setattr(api.settings, "max_upload_bytes", 10)
    assert up(client, "s.kml", kml_bytes).status_code == 413


def test_list_files(client, kml_bytes, shp_zip):
    up(client, "a.kml", kml_bytes)
    up(client, "b.zip", shp_zip)
    listing = client.get("/api/files/").json()
    assert len(listing) == 2
    # Most recent first
    assert listing[0]["filename"] == "b.zip"
    # Pagination: limit=1
    page = client.get("/api/files/?limit=1&offset=1").json()
    assert len(page) == 1 and page[0]["filename"] == "a.kml"


def test_include_geometry_measurements(client, kml_bytes):
    fid = up(client, "s.kml", kml_bytes).json()["id"]
    # Default: include_geometry=false -> geometry is null
    m_no_geom = client.get(f"/api/files/{fid}/measurements/").json()
    assert all(item["geometry"] is None for item in m_no_geom["items"])
    # Explicit: include_geometry=true -> geometry is present for measurable features
    m_with_geom = client.get(f"/api/files/{fid}/measurements/?include_geometry=true").json()
    geom_items = [item for item in m_with_geom["items"] if item["geometry"] is not None]
    assert len(geom_items) >= 1
    assert geom_items[0]["geometry"]["type"] in ("Polygon", "LineString", "Point")


def test_include_geometry_features(client, kml_bytes):
    fid = up(client, "s.kml", kml_bytes).json()["id"]
    # Default: include_geometry=true -> geometry is present
    f_with = client.get(f"/api/files/{fid}/features/").json()
    assert all(item["geometry"] is not None for item in f_with["items"])
    # Explicit: include_geometry=false -> geometry is null
    f_without = client.get(f"/api/files/{fid}/features/?include_geometry=false").json()
    assert all(item["geometry"] is None for item in f_without["items"])
