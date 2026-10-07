"""
Complete end-to-end workflow verification for the Geospatial File Measurement API.
Works seamlessly:
- Hits live server at http://127.0.0.1:8000 if running.
- If server is stopped, automatically runs against FastAPI application in-process.
"""

import json
import sys
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import httpx
from shapely.geometry import box


def banner(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def step(num: str, desc: str):
    print(f"\n[STEP {num}] {desc}")


def get_test_client():
    # 1. Try connecting to live server
    try:
        live_client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=3.0)
        r = live_client.get("/health")
        if r.status_code == 200:
            print("[INFO] Connected to LIVE server at http://127.0.0.1:8000")
            return live_client
    except Exception:
        pass

    # 2. Fallback to in-process FastAPI TestClient
    print("[INFO] Live server not running on port 8000. Running test in-process via FastAPI TestClient...")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def run():
    client = get_test_client()

    # 0. Health check
    banner("0. SERVICE CONNECTIVITY CHECK")
    r = client.get("/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print(f"Service health check passed -> HTTP {r.status_code} {r.json()}")

    # 1. KML Workflow
    banner("1. WORKFLOW: KML FILE INGESTION & MEASUREMENT")
    step("1.1", "Upload KML file (POST /api/files/)")
    kml_path = Path("samples/sample.kml")
    with open(kml_path, "rb") as f:
        r = client.post(
            "/api/files/",
            files={"file": ("sample.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    kml_file = r.json()
    kml_id = kml_file["id"]
    print(f"Status: {r.status_code} Created")
    print("Response JSON:")
    print(json.dumps(kml_file, indent=2))
    assert kml_file["status"] == "COMPLETED"
    assert kml_file["feature_count"] == 3
    assert kml_file["crs"] == "EPSG:4326"

    step("1.2", f"Retrieve File Metadata (GET /api/files/{kml_id}/)")
    r = client.get(f"/api/files/{kml_id}/")
    assert r.status_code == 200
    print(f"Status: {r.status_code} OK")
    print(json.dumps(r.json(), indent=2))

    step("1.3", f"Extract Features & Properties (GET /api/files/{kml_id}/features/)")
    r = client.get(f"/api/files/{kml_id}/features/")
    assert r.status_code == 200
    features_data = r.json()
    print(f"Total features extracted: {features_data['total']}")
    for f in features_data["items"]:
        print(f"  - Index {f['index']}: Type='{f['geometry_type']}', CRS='{f['crs']}', Properties={f['properties']}")
        assert f["geometry"] is not None
        assert f["geometry_type"] in ["Polygon", "LineString", "Point"]

    step("1.4", f"Retrieve Measurements (GET /api/files/{kml_id}/measurements/)")
    r = client.get(f"/api/files/{kml_id}/measurements/")
    assert r.status_code == 200
    m_data = r.json()
    print(f"Status: {r.status_code} OK")
    print("\nSummary Metrics:")
    print(f"  Total Area (m2): {m_data['summary']['total_area_m2']:,.2f} m2")
    print(f"  Total Area (ha): {m_data['summary']['total_area_ha']:.2f} ha")
    print(f"  Total Length (m): {m_data['summary']['total_length_m']:.2f} m")
    print(f"  By Geometry: {m_data['summary']['by_geometry_type']}")

    print("\nIndividual Feature Measurements:")
    for item in m_data["items"]:
        gt = item["geometry_type"]
        st = item["status"]
        if gt == "Polygon":
            print(
                f"  [POLYGON] Area = {item['area_m2']:,.2f} m2 ({item['area_ha']:.2f} ha), Perimeter = {item['perimeter_m']:.2f} m, Projected CRS = {item['projected_crs']}"
            )
            assert st == "MEASURED"
            assert item["area_m2"] > 1_000_000  # Proves metric projection, not degrees!
            assert item["projected_crs"] == "EPSG:32643"
            # Geodesic verification
            diff_pct = abs(item["area_m2"] - item["geodesic_area_m2"]) / item["area_m2"] * 100
            print(f"            Independent Geodesic Area = {item['geodesic_area_m2']:,.2f} m2 (Diff: {diff_pct:.3f}%)")
            assert diff_pct < 0.5
        elif gt == "LineString":
            print(f"  [LINESTRING] Length = {item['length_m']:.2f} m, Projected CRS = {item['projected_crs']}")
            assert st == "MEASURED"
            assert item["length_m"] > 1000
        elif gt == "Point":
            print(f"  [POINT] Status = {st} (No measurement required)")
            assert st == "NOT_APPLICABLE"
            assert item["area_m2"] is None and item["length_m"] is None

    # 2. Shapefile Workflow
    banner("2. WORKFLOW: SHAPEFILE (.ZIP) INGESTION & MEASUREMENT")
    step("2.1", "Upload Shapefile zip (POST /api/files/)")
    shp_path = Path("samples/sample_shapefile.zip")
    with open(shp_path, "rb") as f:
        r = client.post(
            "/api/files/",
            files={"file": ("sample_shapefile.zip", f, "application/zip")},
        )
    assert r.status_code == 201
    shp_file = r.json()
    shp_id = shp_file["id"]
    print(f"Status: {r.status_code} Created (File ID: {shp_id})")
    assert shp_file["file_type"] == "SHAPEFILE"
    assert shp_file["feature_count"] == 2

    step("2.2", "Retrieve Shapefile Measurements with Pagination & Filter")
    r = client.get(f"/api/files/{shp_id}/measurements/?geometry_type=Polygon&limit=1&offset=0")
    assert r.status_code == 200
    page = r.json()
    print(f"Total: {page['total']}, Page count: {len(page['items'])}, First index: {page['items'][0]['index']}")
    assert page["total"] == 2
    assert len(page["items"]) == 1

    # 3. Graceful Handling & Error Handling
    banner("3. WORKFLOW: ERROR HANDLING & EDGE CASES")
    step("3.1", "Reject unsupported file extension (.txt)")
    r = client.post("/api/files/", files={"file": ("notes.txt", b"plain text", "text/plain")})
    assert r.status_code == 422
    detail = r.json()["detail"]
    code = detail["code"] if isinstance(detail, dict) else detail[0]["type"]
    print(f"Status: {r.status_code} Unprocessable Entity -> Code: {code}")
    assert "UNSUPPORTED_FILE_TYPE" in str(detail)

    step("3.2", "Reject Shapefile zip missing .prj (Coordinate Reference System)")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        gdf = gpd.GeoDataFrame(
            {"name": ["parcel"]},
            geometry=[box(77.5, 12.9, 77.51, 12.91)],
            crs="EPSG:4326",
        )
        gdf.to_file(p / "missing_prj.shp")
        (p / "missing_prj.prj").unlink()
        zip_p = p / "missing_prj.zip"
        with zipfile.ZipFile(zip_p, "w") as z:
            for x in p.glob("missing_prj.*"):
                if x.suffix != ".zip":
                    z.write(x, x.name)
        with open(zip_p, "rb") as f:
            r = client.post("/api/files/", files={"file": ("missing_prj.zip", f)})
        assert r.status_code == 422
        print(f"Status: {r.status_code} -> Code: {r.json()['detail']['code']}")
        assert r.json()["detail"]["code"] == "MISSING_CRS"

        step("3.3", "Recover missing .prj with ?assume_crs=EPSG:4326 query parameter")
        with open(zip_p, "rb") as f:
            r = client.post(
                "/api/files/?assume_crs=EPSG:4326",
                files={"file": ("missing_prj.zip", f)},
            )
        assert r.status_code == 201
        print(f"Status: {r.status_code} Created -> Override successful, Status: {r.json()['status']}")
        assert r.json()["status"] == "COMPLETED"

    step("3.4", "Handle corrupted KML gracefully (Record FAILED lifecycle)")
    r = client.post("/api/files/", files={"file": ("corrupt.kml", b"not kml content at all")})
    assert r.status_code == 422
    err_fid = r.json()["detail"]["file_id"]
    print(f"Recorded FAILED status for File ID {err_fid}")
    # Verify file is recorded as FAILED
    r_check = client.get(f"/api/files/{err_fid}/")
    assert r_check.json()["status"] == "FAILED"
    # Querying measurements on unready file gives 409 Conflict
    r_meas = client.get(f"/api/files/{err_fid}/measurements/")
    assert r_meas.status_code == 409
    print(f"GET /measurements/ on FAILED file returns HTTP {r_meas.status_code} {r_meas.json()['detail']['code']}")

    step("3.5", "Query non-existent file ID (404)")
    r = client.get("/api/files/nonexistent_id/")
    assert r.status_code == 404
    print(f"GET /api/files/nonexistent_id/ -> HTTP {r.status_code} {r.json()['detail']['code']}")

    step("3.6", "Delete file and cascade database cleanup (DELETE /api/files/{id}/)")
    r = client.delete(f"/api/files/{kml_id}/")
    assert r.status_code == 204
    print(f"DELETE /api/files/{kml_id}/ -> HTTP {r.status_code} No Content")
    # Subsequent GET returns 404
    r_after = client.get(f"/api/files/{kml_id}/")
    assert r_after.status_code == 404
    print(f"Verifying deleted file: GET /api/files/{kml_id}/ -> HTTP {r_after.status_code} Not Found")

    banner("WORKFLOW VERIFICATION COMPLETE: ALL REQUIREMENTS 100% PASSING!")


if __name__ == "__main__":
    run()
