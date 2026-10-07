import tempfile
import zipfile
import pathlib
import geopandas as gpd
from shapely.geometry import box
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("--- Acceptance Checklist Verification ---")

# 1. /docs loads
r_docs = client.get("/docs")
assert r_docs.status_code == 200, f"Docs failed: {r_docs.status_code}"
print("[OK] Check 1: /docs loads -> PASS (200 OK)")

# 2. Upload sample.kml: polygon area ~1.2 km2, projected_crs = EPSG:32643
with open("samples/sample.kml", "rb") as f:
    r_kml = client.post("/api/files/", files={"file": ("sample.kml", f)})
assert r_kml.status_code == 201, f"KML upload failed: {r_kml.status_code}"
kml_id = r_kml.json()["id"]
m_kml = client.get(f"/api/files/{kml_id}/measurements/").json()
poly = [i for i in m_kml["items"] if i["geometry_type"] == "Polygon"][0]
print(f"[OK] Check 2: KML polygon area = {poly['area_m2']:.2f} m2 ({poly['area_ha']:.2f} ha), projected_crs = {poly['projected_crs']}")
assert 1_180_000 < poly["area_m2"] < 1_220_000
assert poly["projected_crs"] == "EPSG:32643"
print("     -> Polygon area ~1.2 km2 (120 ha) and EPSG:32643 verified -> PASS")

# 3. Upload sample_shapefile.zip: 2 polygons measured
with open("samples/sample_shapefile.zip", "rb") as f:
    r_shp = client.post("/api/files/", files={"file": ("sample_shapefile.zip", f)})
assert r_shp.status_code == 201
shp_id = r_shp.json()["id"]
m_shp = client.get(f"/api/files/{shp_id}/measurements/").json()
measured_polys = [i for i in m_shp["items"] if i["geometry_type"] == "Polygon" and i["status"] == "MEASURED"]
assert len(measured_polys) == 2
print(f"[OK] Check 3: Shapefile measured polygons count = {len(measured_polys)} -> PASS")

# 4. Upload .txt gives 422 UNSUPPORTED_FILE_TYPE
r_txt = client.post("/api/files/", files={"file": ("test.txt", b"hello")})
assert r_txt.status_code == 422
assert r_txt.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"
print("[OK] Check 4: Upload .txt gives 422 UNSUPPORTED_FILE_TYPE -> PASS")

# 5. Missing .prj gives 422 MISSING_CRS; ?assume_crs=EPSG:4326 succeeds
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td)
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[box(77.5, 12.9, 77.51, 12.91)], crs="EPSG:4326")
    gdf.to_file(p / "noprj.shp")
    (p / "noprj.prj").unlink()
    zpath = p / "noprj.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for x in p.glob("noprj.*"):
            if x.suffix != ".zip":
                z.write(x, x.name)
    with open(zpath, "rb") as f:
        r_noprj = client.post("/api/files/", files={"file": ("noprj.zip", f)})
    assert r_noprj.status_code == 422
    assert r_noprj.json()["detail"]["code"] == "MISSING_CRS"
    print("[OK] Check 5a: Shapefile missing .prj gives 422 MISSING_CRS -> PASS")

    with open(zpath, "rb") as f:
        r_assume = client.post("/api/files/?assume_crs=EPSG:4326", files={"file": ("noprj.zip", f)})
    assert r_assume.status_code == 201
    assert r_assume.json()["status"] == "COMPLETED"
    print("[OK] Check 5b: Shapefile missing .prj with ?assume_crs=EPSG:4326 succeeds -> PASS")

print("\nALL ACCEPTANCE CHECKLIST ITEMS FULLY VERIFIED AND PASSING!")
