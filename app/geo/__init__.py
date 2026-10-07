"""Geospatial processing domain package.

Public surface — all pure functions, zero framework dependencies:

- **reader**: KML / zipped-Shapefile → ``ParsedFile``
- **measure**: Geometry → metric ``Measurement``
- **crs**: Projected CRS selection (UTM / polar)
- **errors**: ``GeoFileError`` for client-fixable problems
"""

__all__ = ["crs", "errors", "measure", "reader"]
