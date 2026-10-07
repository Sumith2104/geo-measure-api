import zipfile
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box

out = Path("samples")
out.mkdir(exist_ok=True)

# Generate sample Shapefile zip
gdf = gpd.GeoDataFrame(
    {"name": ["Field A", "Field B"], "crop": ["wheat", "rice"]},
    geometry=[box(77.500, 12.900, 77.510, 12.910), box(77.520, 12.900, 77.535, 12.912)],
    crs="EPSG:4326"
)
tmp = out / "_shp"
tmp.mkdir(exist_ok=True)
gdf.to_file(tmp / "fields.shp")
with zipfile.ZipFile(out / "sample_shapefile.zip", "w") as z:
    for f in tmp.iterdir():
        z.write(f, f.name)
for f in tmp.iterdir():
    f.unlink()
tmp.rmdir()

# Generate sample KML
KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <Placemark>
    <name>field</name>
    <Polygon>
      <outerBoundaryIs>
        <LinearRing>
          <coordinates>
            77.5,12.9,0 77.51,12.9,0 77.51,12.91,0 77.5,12.91,0 77.5,12.9,0
          </coordinates>
        </LinearRing>
      </outerBoundaryIs>
    </Polygon>
  </Placemark>
  <Placemark>
    <name>road</name>
    <LineString>
      <coordinates>
        77.5,12.9,0 77.51,12.9,0
      </coordinates>
    </LineString>
  </Placemark>
  <Placemark>
    <name>well</name>
    <Point>
      <coordinates>
        77.5,12.9,0
      </coordinates>
    </Point>
  </Placemark>
</Document>
</kml>"""

(out / "sample.kml").write_text(KML.strip(), encoding="utf-8")
print("Sample files created in samples/ successfully.")
