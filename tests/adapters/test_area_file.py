# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a survey area from KML, KMZ, shapefiles and GeoJSON (fictional places only)."""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import pytest
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon

from avispria.adapters.area_file import (
    AreaFileError,
    area_from_file,
    read_area_file,
    shp_polygons,
)
from avispria.core.geometry import LocalFrame

LON, LAT = 10.0, 45.0
D = 0.001  # about 80 m east-west, 110 m north-south
SQUARE = [(LON, LAT), (LON, LAT + D), (LON + D, LAT + D), (LON + D, LAT), (LON, LAT)]  # clockwise
HOLE = [(LON + 3e-4, LAT + 3e-4), (LON + 6e-4, LAT + 3e-4), (LON + 6e-4, LAT + 6e-4),
        (LON + 3e-4, LAT + 6e-4), (LON + 3e-4, LAT + 3e-4)]  # fmt: skip


def shp_bytes(rings: list[list[tuple[float, float]]], kind: int = 5) -> bytes:
    """A one-record shapefile holding ``rings`` as one polygon."""
    points = [p for r in rings for p in r]
    parts, at = [], 0
    for r in rings:
        parts.append(at)
        at += len(r)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    content = struct.pack(
        "<i4d2i", kind, min(xs), min(ys), max(xs), max(ys), len(rings), len(points)
    )
    content += struct.pack(f"<{len(parts)}i", *parts)
    content += b"".join(struct.pack("<2d", *p) for p in points)
    record = struct.pack(">2i", 1, len(content) // 2) + content
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(record)) // 2)
    header += struct.pack("<2i4d4d", 1000, kind, min(xs), min(ys), max(xs), max(ys), 0, 0, 0, 0)
    return header + record


def area_m2(geom: Polygon) -> float:
    return LocalFrame.for_polygon(geom).polygon_to_local(geom).area


def test_a_shapefile_with_a_hole_and_its_parts_found_by_themselves(tmp_path: Path) -> None:
    shp = tmp_path / "plot.shp"
    shp.write_bytes(shp_bytes([SQUARE, HOLE]))
    (tmp_path / "plot.SHX").write_bytes(b"x")
    (tmp_path / "plot.dbf").write_bytes(b"x")
    (tmp_path / "plot.prj").write_text(CRS.from_epsg(4326).to_wkt(), encoding="utf-8")
    found = read_area_file(shp)
    assert len(found.polygons) == 1 and len(found.polygons[0].interiors) == 1
    assert ".shx" in found.notes[0] and ".prj" in found.notes[0] and ".dbf" in found.notes[0]


def test_a_projected_shapefile_is_moved_to_longitude_and_latitude(tmp_path: Path) -> None:
    utm = CRS.from_epsg(32632)
    to_utm = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    ring = [to_utm.transform(x, y) for x, y in SQUARE]
    (tmp_path / "plot.shp").write_bytes(shp_bytes([ring]))
    (tmp_path / "plot.prj").write_text(utm.to_wkt(), encoding="utf-8")
    poly = read_area_file(tmp_path / "plot.shp").polygons[0]
    assert poly.bounds == pytest.approx((LON, LAT, LON + D, LAT + D), abs=1e-7)


def test_a_projected_shapefile_without_its_prj_is_refused(tmp_path: Path) -> None:
    corners = [(0, 0), (0, 90), (90, 90), (90, 0), (0, 0)]
    (tmp_path / "plot.shp").write_bytes(shp_bytes([[(5e5 + x, 4.9e6 + y) for x, y in corners]]))
    with pytest.raises(AreaFileError, match=r"\.prj"):
        read_area_file(tmp_path / "plot.shp")


def test_lines_and_broken_files_are_explained(tmp_path: Path) -> None:
    (tmp_path / "road.shp").write_bytes(shp_bytes([SQUARE], kind=3))
    with pytest.raises(AreaFileError, match="lines"):
        read_area_file(tmp_path / "road.shp")
    with pytest.raises(AreaFileError, match="not a shapefile"):
        shp_polygons(b"nonsense")
    (tmp_path / "x.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(AreaFileError, match="reads"):
        read_area_file(tmp_path / "x.txt")


KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>
<outerBoundaryIs><LinearRing><coordinates>{outer}</coordinates></LinearRing></outerBoundaryIs>
<innerBoundaryIs><LinearRing><coordinates>{hole}</coordinates></LinearRing></innerBoundaryIs>
</Polygon></Placemark></Document></kml>"""


def kml_text() -> str:
    def ring(r: list[tuple[float, float]]) -> str:
        return " ".join(f"{x},{y},0" for x, y in r)

    return KML.format(outer=ring(SQUARE), hole=ring(HOLE))


def test_kml_kmz_and_a_zipped_shapefile_are_read(tmp_path: Path) -> None:
    (tmp_path / "a.kml").write_text(kml_text(), encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "a.kmz", "w") as z:
        z.writestr("doc.kml", kml_text())
    with zipfile.ZipFile(tmp_path / "s.zip", "w") as z:
        z.writestr("folder/plot.shp", shp_bytes([SQUARE]))
        z.writestr("folder/plot.prj", CRS.from_epsg(4326).to_wkt())
    for name in ("a.kml", "a.kmz"):
        (poly,) = read_area_file(tmp_path / name).polygons
        assert len(poly.interiors) == 1
    assert len(read_area_file(tmp_path / "s.zip").polygons) == 1


def test_a_dji_mission_has_no_area(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / "mission.kmz", "w") as z:
        z.writestr(
            "wpmz/template.kml", '<kml xmlns="http://www.opengis.net/kml/2.2"><Point/></kml>'
        )
    with pytest.raises(AreaFileError, match="only waypoints"):
        read_area_file(tmp_path / "mission.kmz")


def test_geojson_multipolygons_and_a_buffer(tmp_path: Path) -> None:
    far = [(x + 0.01, y) for x, y in SQUARE]
    doc = {"type": "MultiPolygon", "coordinates": [[SQUARE], [far]]}
    (tmp_path / "two.geojson").write_text(json.dumps(doc), encoding="utf-8")
    area, _ = area_from_file(tmp_path / "two.geojson")
    assert isinstance(area, MultiPolygon)
    (tmp_path / "one.geojson").write_text(json.dumps({"type": "Polygon", "coordinates": [SQUARE]}))
    exact, _ = area_from_file(tmp_path / "one.geojson")
    wide, _ = area_from_file(tmp_path / "one.geojson", buffer_m=20.0)
    assert isinstance(exact, Polygon) and isinstance(wide, Polygon)
    a, b = area_m2(exact), area_m2(wide)
    side_x, side_y = 78.8, 111.1  # metres, roughly, at 45 degrees
    assert b == pytest.approx((side_x + 40) * (side_y + 40), rel=0.03)
    assert a == pytest.approx(side_x * side_y, rel=0.03)
    with pytest.raises(AreaFileError, match="buffer"):
        area_from_file(tmp_path / "one.geojson", buffer_m=-1)
