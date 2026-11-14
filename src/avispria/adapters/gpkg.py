# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write a GeoPackage (OGC 12-128r18) with Python's own SQLite: no GDAL vector library needed.

A GeoPackage is one SQLite file that QGIS, ArcGIS and GDAL open directly, holds several layers
with their attributes and coordinate system, and can be edited in place. QGIS also reads layer
styles from a ``layer_styles`` table in the file, so the layers open already styled.
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import shapely
from pyproj import CRS

APPLICATION_ID = 0x47504B47  # "GPKG"
USER_VERSION = 10400  # GeoPackage 1.4
LITTLE_ENDIAN_XY_ENVELOPE = 0b0000_0011  # byte order 1, envelope type 1 (minx, maxx, miny, maxy)
LOCAL_SRS_ID = 100_000  # a coordinate system without an EPSG code


class GpkgError(ValueError):
    """The GeoPackage could not be written; the message says why."""


@dataclass
class Layer:
    name: str  # table name: letters, digits and underscores
    kind: str  # POINT, LINESTRING or POLYGON (MULTIPOLYGON for mixed)
    geometries: list[shapely.Geometry]
    attributes: list[dict[str, Any]] = field(default_factory=list)  # one per geometry
    description: str = ""
    style_qml: str = ""  # QGIS default style


SRS_DEFAULTS = (
    ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", "undefined cartesian"),
    ("Undefined geographic SRS", 0, "NONE", 0, "undefined", "undefined geographic"),
)


def _srs(crs: CRS) -> tuple[int, str, int, str, str]:
    code = crs.to_epsg()
    if code is not None:
        return code, "EPSG", code, crs.name, crs.to_wkt()
    return LOCAL_SRS_ID, "NONE", LOCAL_SRS_ID, crs.name or "local", crs.to_wkt()


def geometry_blob(geom: shapely.Geometry, srs_id: int) -> bytes:
    """The GeoPackage binary geometry: header, envelope, then little-endian ISO WKB."""
    if geom.is_empty:
        return b"GP" + bytes([0, 0b0001_0001]) + struct.pack("<i", srs_id) + shapely.to_wkb(geom)
    minx, miny, maxx, maxy = geom.bounds
    header = b"GP" + bytes([0, LITTLE_ENDIAN_XY_ENVELOPE]) + struct.pack("<i", srs_id)
    envelope = struct.pack("<4d", minx, maxx, miny, maxy)
    return header + envelope + shapely.to_wkb(geom, byte_order=1, flavor="iso")


def _column_type(values: Sequence[Any]) -> str:
    found = [v for v in values if v is not None]
    if found and all(isinstance(v, bool) for v in found):
        return "BOOLEAN"
    if found and all(isinstance(v, int) and not isinstance(v, bool) for v in found):
        return "INTEGER"
    if found and all(isinstance(v, int | float) and not isinstance(v, bool) for v in found):
        return "REAL"
    return "TEXT"


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _base_tables(db: sqlite3.Connection) -> None:
    db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    db.execute(f"PRAGMA user_version = {USER_VERSION}")
    db.execute(
        "CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, "
        "organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, "
        "definition TEXT NOT NULL, description TEXT)"
    )
    db.execute(
        "CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT "
        "NULL, identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL "
        "DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, "
        "max_y DOUBLE, srs_id INTEGER, CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES "
        "gpkg_spatial_ref_sys(srs_id))"
    )
    db.execute(
        "CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, "
        "geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT "
        "NOT NULL, CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name), "
        "CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name), "
        "CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys (srs_id))"
    )
    wgs84 = CRS.from_epsg(4326)
    db.execute(
        "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
        ("WGS 84 geodetic", 4326, "EPSG", 4326, wgs84.to_wkt(), "longitude/latitude WGS 84"),
    )
    db.executemany("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)", SRS_DEFAULTS)
    db.execute(
        "CREATE TABLE layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog "
        "TEXT(256), f_table_schema TEXT(256), f_table_name TEXT(256), f_geometry_column "
        "TEXT(256), styleName TEXT(30), styleQML TEXT, styleSLD TEXT, useAsDefault BOOLEAN, "
        "description TEXT, owner TEXT(30), ui TEXT(30), update_time DATETIME DEFAULT "
        "CURRENT_TIMESTAMP)"
    )
    db.execute(
        "INSERT INTO gpkg_contents (table_name, data_type, identifier) "
        "VALUES ('layer_styles', 'attributes', 'layer_styles')"
    )


def _layer(db: sqlite3.Connection, layer: Layer, srs_id: int) -> None:
    if not layer.name.replace("_", "").isalnum():
        raise GpkgError(f"layer name {layer.name!r}: use letters, digits and underscores")
    if layer.attributes and len(layer.attributes) != len(layer.geometries):
        raise GpkgError(f"layer {layer.name}: one row of attributes per geometry")
    rows: Sequence[Mapping[str, Any]] = layer.attributes or [{} for _ in layer.geometries]
    names = list(dict.fromkeys(k for row in rows for k in row))
    if any(n.lower() in {"fid", "geom"} for n in names):
        raise GpkgError(f"layer {layer.name}: 'fid' and 'geom' are reserved column names")
    types = {n: _column_type([row.get(n) for row in rows]) for n in names}
    columns = "".join(f", {_quote(n)} {types[n]}" for n in names)
    db.execute(
        f"CREATE TABLE {_quote(layer.name)} (fid INTEGER PRIMARY KEY AUTOINCREMENT, "
        f"geom {layer.kind}{columns})"
    )
    bounds = shapely.total_bounds(layer.geometries) if layer.geometries else [None] * 4
    db.execute(
        "INSERT INTO gpkg_contents (table_name, data_type, identifier, description, min_x, "
        "min_y, max_x, max_y, srs_id) VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?)",
        (layer.name, layer.name, layer.description, *map(_finite, bounds), srs_id),
    )
    db.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
        (layer.name, layer.kind, srs_id),
    )
    marks = ", ".join("?" for _ in range(len(names) + 1))
    insert = f"INSERT INTO {_quote(layer.name)} (geom{''.join(', ' + _quote(n) for n in names)})"
    db.executemany(
        f"{insert} VALUES ({marks})",
        [
            (geometry_blob(g, srs_id), *(_plain(row.get(n)) for n in names))
            for g, row in zip(layer.geometries, rows, strict=True)
        ],
    )
    if layer.style_qml:
        db.execute(
            "INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, "
            "f_geometry_column, styleName, styleQML, styleSLD, useAsDefault, description, owner) "
            "VALUES ('', '', ?, 'geom', ?, ?, '', 1, 'Dīvi default', '')",
            (layer.name, layer.name, layer.style_qml),
        )


def _finite(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and value == value else None


def _plain(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    return value if value is None or isinstance(value, int | float | str) else str(value)


def write_gpkg(path: Path, layers: Sequence[Layer], crs: CRS) -> Path:
    """Write ``layers`` (all in ``crs``) to a new GeoPackage, replacing an old one."""
    part = path.with_suffix(".part")
    part.unlink(missing_ok=True)
    srs_id, org, code, name, wkt = _srs(crs)
    # closed in every case: sqlite3's own "with" commits but leaves the file open, and Windows
    # cannot delete or replace a file that is still open
    try:
        db = sqlite3.connect(part)
    except sqlite3.Error as exc:
        raise GpkgError(f"the GeoPackage could not be written: {exc}") from None
    try:
        with db:
            _base_tables(db)
            if srs_id != 4326:
                db.execute(
                    "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
                    (name, srs_id, org, code, wkt, name),
                )
            for layer in layers:
                _layer(db, layer, srs_id)
    except sqlite3.Error as exc:
        db.close()
        part.unlink(missing_ok=True)
        raise GpkgError(f"the GeoPackage could not be written: {exc}") from None
    except GpkgError:
        db.close()
        part.unlink(missing_ok=True)
        raise
    db.close()
    try:
        part.replace(path)
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise GpkgError(f"the GeoPackage could not be written: {exc}") from None
    return path
