import zipfile, shutil, os, pytest, geopandas as gpd
from shapely.geometry import box, Point
from app.geo.reader import read_kml, read_shapefile_zip
from app.geo.errors import GeoFileError

KML_MULTI_FOLDER = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <Folder>
    <name>Folder 1</name>
    <Placemark>
      <name>P1</name>
      <ExtendedData><Data name="k"><value>v</value></Data></ExtendedData>
      <Point><coordinates>77.5,12.9,0</coordinates></Point>
    </Placemark>
  </Folder>
  <Folder>
    <name>Folder 2</name>
    <Placemark><name>P2</name><Point><coordinates>77.51,12.91,0</coordinates></Point></Placemark>
    <Placemark><name>P3</name><Point><coordinates>77.52,12.92,0</coordinates></Point></Placemark>
  </Folder>
</Document>
</kml>"""

def test_kml_all_folders(tmp_path):
    kml_file = tmp_path / "t.kml"
    kml_file.write_text(KML_MULTI_FOLDER, encoding="utf-8")
    p = read_kml(kml_file)
    assert len(p.features) == 3 and p.crs.to_epsg() == 4326
    assert p.features[0].properties["k"] == "v" and [f.index for f in p.features] == [0, 1, 2]

def mk(tmp_path, crs="EPSG:4326", prj=True):
    gdf = gpd.GeoDataFrame({"name":["a","b"]}, geometry=[box(77.5,12.9,77.51,12.91), box(77.52,12.9,77.53,12.91)], crs=crs)
    d = tmp_path/"s"; d.mkdir(); gdf.to_file(d/"x.shp")
    if not prj: os.remove(d/"x.prj")
    z = tmp_path/"x.zip"
    with zipfile.ZipFile(z,"w") as zf:
        for f in d.iterdir(): zf.write(f, "nested/"+f.name)
    return z

def test_shp(tmp_path):
    p = read_shapefile_zip(mk(tmp_path), max_uncompressed=10**8, max_entries=50)
    assert len(p.features)==2 and p.crs.to_epsg()==4326

def test_missing_prj(tmp_path):
    z = mk(tmp_path, prj=False)
    with pytest.raises(GeoFileError) as e: read_shapefile_zip(z, max_uncompressed=10**8, max_entries=50)
    assert e.value.code=="MISSING_CRS"
    assert len(read_shapefile_zip(z, max_uncompressed=10**8, max_entries=50, assume_crs="EPSG:4326").features)==2

def test_zip_slip_and_bomb(tmp_path):
    z = tmp_path/"e.zip"
    with zipfile.ZipFile(z,"w") as zf: zf.writestr("../../evil.shp","x")
    with pytest.raises(GeoFileError): read_shapefile_zip(z, max_uncompressed=10**8, max_entries=50)
    assert not (tmp_path.parent/"evil.shp").exists()
    with pytest.raises(GeoFileError) as e: read_shapefile_zip(mk(tmp_path), max_uncompressed=10, max_entries=50)
    assert e.value.code=="ZIP_TOO_LARGE"
