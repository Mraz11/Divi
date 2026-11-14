# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read a survey area from a map file: KML, KMZ, a shapefile (or a .zip with one), or GeoJSON.

Every reader returns the polygons in longitude/latitude (WGS 84) and a few notes on what was
found. A shapefile is several files with the same name; the others (.shx, .dbf, .prj, .cpg) are
found next to the .shp by themselves. Only the .shp (the shapes) and the .prj (where on Earth
the numbers are) are needed; without a .prj the numbers must already be longitude and latitude.

``area_from_file`` joins the polygons into one area and can widen it by a buffer in metres, so
the photos also cover a strip around the shape.
"""

from __future__ import annotations

import io
import json
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry import LinearRing, MultiPolygon, Polygon, shape
from shapely.ops import unary_union

from avispria.adapters.safe_files import UnsafeFile, check_size, parse_xml, read_members
from avispria.core.geometry import LocalFrame

SUFFIXES = (".kml", ".kmz", ".shp", ".zip", ".geojson", ".json")
SHAPEFILE_PARTS = (".shx", ".dbf", ".prj", ".cpg")
POLYGON_TYPES = {5: "polygon", 15: "polygon with heights", 25: "polygon with measures"}
OTHER_TYPES = {1: "points", 3: "lines", 8: "points", 11: "points", 13: "lines", 21: "points"}
MAX_BUFFER_M = 5_000.0


class AreaFileError(ValueError):
    """The file cannot give a survey area; the message says why in plain words."""


@dataclass(frozen=True)
class AreaFile:
    polygons: tuple[Polygon, ...]  # longitude/latitude
    notes: tuple[str, ...] = ()


# ------------------------------------------------------------------------------------ KML
def _ring(text: str | None) -> list[tuple[float, float]]:
    points = []
    for item in (text or "").split():
        parts = item.split(",")
        if len(parts) >= 2:
            points.append((float(parts[0]), float(parts[1])))
    return points


def _kml_polygons(data: bytes) -> list[Polygon]:
    try:
        root = parse_xml(data, "the KML file")
    except UnsafeFile as exc:
        raise AreaFileError(str(exc)) from None
    polygons = []
    for node in root.iter("{*}Polygon"):
        outer = node.find(".//{*}outerBoundaryIs//{*}coordinates")
        if outer is None:
            continue
        holes = [_ring(c.text) for c in node.findall(".//{*}innerBoundaryIs//{*}coordinates")]
        shell = _ring(outer.text)
        if len(shell) >= 3:
            polygons.append(Polygon(shell, [h for h in holes if len(h) >= 3]))
    return polygons


def _kmz_polygons(data: bytes) -> list[Polygon]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
            names.sort(key=lambda n: (Path(n).name.lower() != "doc.kml", n))
            found = read_members(archive, names)
    except UnsafeFile as exc:
        raise AreaFileError(str(exc)) from None
    polygons: list[Polygon] = []
    for name in names:
        polygons += _kml_polygons(found[name])
    return polygons


# ------------------------------------------------------------------------------ shapefile
def shp_polygons(data: bytes) -> list[Polygon]:
    """The polygons of a .shp file's bytes, in the file's own coordinates."""
    if len(data) < 100 or struct.unpack(">i", data[:4])[0] != 9994:
        raise AreaFileError("it is not a shapefile (.shp)")
    kind = struct.unpack("<i", data[32:36])[0]
    if kind in OTHER_TYPES:
        raise AreaFileError(f"the shapefile holds {OTHER_TYPES[kind]}, not areas (polygons)")
    if kind not in POLYGON_TYPES:
        raise AreaFileError(f"the shapefile has a shape type Dīvi cannot read ({kind})")
    polygons: list[Polygon] = []
    at = 100
    while at + 8 <= len(data):
        length = struct.unpack(">i", data[at + 4 : at + 8])[0] * 2
        content = data[at + 8 : at + 8 + length]
        at += 8 + length
        if len(content) < 44 or struct.unpack("<i", content[:4])[0] == 0:
            continue  # a deleted (null) shape
        parts_n, points_n = struct.unpack("<ii", content[36:44])
        parts = list(struct.unpack(f"<{parts_n}i", content[44 : 44 + 4 * parts_n]))
        start = 44 + 4 * parts_n
        xy = struct.unpack(f"<{2 * points_n}d", content[start : start + 16 * points_n])
        points = list(zip(xy[0::2], xy[1::2], strict=True))
        rings = [points[a:b] for a, b in zip(parts, [*parts[1:], points_n], strict=True)]
        polygons += _assemble([r for r in rings if len(r) >= 4])
    return polygons


def _assemble(rings: list[list[tuple[float, float]]]) -> list[Polygon]:
    """Shapefile rings: clockwise ones are outlines, the others holes in the outline around them."""
    outers = [r for r in rings if not LinearRing(r).is_ccw]
    holes = [r for r in rings if LinearRing(r).is_ccw]
    if not outers:  # written the wrong way round: take every ring as an outline
        return [Polygon(r) for r in rings]
    shells = [Polygon(r) for r in outers]
    inner: list[list[list[tuple[float, float]]]] = [[] for _ in outers]
    for hole in holes:
        probe = Polygon(hole).representative_point()
        n = next((i for i, s in enumerate(shells) if s.contains(probe)), None)
        if n is None:
            shells.append(Polygon(hole))
            inner.append([])
        else:
            inner[n].append(hole)
    return [Polygon(s.exterior.coords, h) for s, h in zip(shells, inner, strict=True)]


def _to_lonlat(polygons: list[Polygon], prj: str | None) -> list[Polygon]:
    if prj is None:
        bounds = unary_union(polygons).bounds if polygons else (0, 0, 0, 0)
        if bounds[0] >= -180 and bounds[2] <= 180 and bounds[1] >= -90 and bounds[3] <= 90:
            return polygons
        raise AreaFileError(
            "the shapefile has no .prj file next to it, so where its numbers are on Earth is "
            "unknown. Copy the .prj file that came with it into the same folder"
        )
    try:
        crs = CRS.from_wkt(prj)
    except CRSError as exc:
        raise AreaFileError(f"its .prj file could not be read ({exc})") from None
    move = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    def forward(coords: Any) -> Any:
        xs, ys = move.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([xs, ys])

    return [shapely.transform(p, forward) for p in polygons]


def _sibling(shp: Path, suffix: str) -> Path | None:
    for candidate in shp.parent.glob(f"{shp.stem}.*"):
        if candidate.suffix.lower() == suffix:
            return candidate
    return None


def _read_shapefile(path: Path) -> AreaFile:
    found = [s for s in SHAPEFILE_PARTS if _sibling(path, s) is not None]
    prj_path = _sibling(path, ".prj")
    prj = prj_path.read_text(encoding="utf-8", errors="replace") if prj_path else None
    polygons = _to_lonlat(shp_polygons(path.read_bytes()), prj)
    notes = [f"shapefile parts found: .shp {' '.join(found)}".rstrip()]
    if prj is None:
        notes.append("no .prj file: the numbers were taken as longitude and latitude")
    return AreaFile(tuple(polygons), tuple(notes))


def _read_zip(path: Path) -> AreaFile:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shps = [n for n in names if n.lower().endswith(".shp")]
        if not shps:
            kml = [n for n in names if n.lower().endswith(".kml")]
            if kml:
                return AreaFile(tuple(_kmz_polygons(path.read_bytes())))
            raise AreaFileError("the .zip file has no shapefile (.shp) or KML file in it")
        base = shps[0][:-4]
        prj_name = next((n for n in names if n.lower() == f"{base.lower()}.prj"), None)
        found = read_members(archive, [shps[0], *([prj_name] if prj_name else [])])
        prj = found[prj_name].decode("utf-8", "replace") if prj_name else None
        polygons = _to_lonlat(shp_polygons(found[shps[0]]), prj)
    return AreaFile(tuple(polygons), (f"read {Path(shps[0]).name} from the .zip file",))


# ---------------------------------------------------------------------------- GeoJSON
def _geojson_polygons(data: Any) -> list[Polygon]:
    items = data.get("features", [data]) if isinstance(data, dict) else []
    polygons: list[Polygon] = []
    for item in items:
        geometry = item.get("geometry", item) if isinstance(item, dict) else None
        if not isinstance(geometry, dict) or "type" not in geometry:
            continue
        try:
            geom = shape(geometry)
        except Exception:  # shapely raises several types for malformed input
            continue
        if isinstance(geom, Polygon):
            polygons.append(geom)
        elif isinstance(geom, MultiPolygon):
            polygons += list(geom.geoms)
    return polygons


# ------------------------------------------------------------------------------- public
def read_area_file(path: Path) -> AreaFile:
    """The polygons in a map file, in longitude/latitude."""
    suffix = path.suffix.lower()
    if suffix not in SUFFIXES:
        raise AreaFileError(f"Dīvi reads {', '.join(SUFFIXES)} files, not {suffix or 'this'}")
    try:
        check_size(path)
        if suffix == ".shp":
            result = _read_shapefile(path)
        elif suffix == ".zip":
            result = _read_zip(path)
        elif suffix == ".kmz":
            result = AreaFile(tuple(_kmz_polygons(path.read_bytes())))
        elif suffix == ".kml":
            result = AreaFile(tuple(_kml_polygons(path.read_bytes())))
        else:
            result = AreaFile(tuple(_geojson_polygons(json.loads(path.read_text("utf-8")))))
    except UnsafeFile as exc:
        raise AreaFileError(str(exc)) from None
    except (OSError, zipfile.BadZipFile, struct.error, ValueError) as exc:
        if isinstance(exc, AreaFileError):
            raise
        raise AreaFileError(f"it could not be read ({exc})") from None
    good = tuple(p if p.is_valid else shapely.make_valid(p) for p in result.polygons)
    polygons = tuple(
        piece
        for p in good
        for piece in (p.geoms if isinstance(p, MultiPolygon) else [p])
        if isinstance(piece, Polygon) and not piece.is_empty and piece.area > 0
    )
    if not polygons:
        raise AreaFileError(
            "it has no area (polygon) in it. A DJI Fly mission file has only waypoints: draw the "
            "area instead, or use a file with the area's outline"
        )
    return AreaFile(polygons, result.notes)


def area_from_file(path: Path, buffer_m: float = 0.0) -> tuple[Polygon | MultiPolygon, AreaFile]:
    """All the polygons of a file as one area, widened by ``buffer_m`` metres on every side."""
    if not 0.0 <= buffer_m <= MAX_BUFFER_M:
        raise AreaFileError(f"the buffer must be between 0 and {MAX_BUFFER_M:.0f} m")
    found = read_area_file(path)
    area = unary_union(found.polygons)
    if buffer_m > 0:
        area = buffered(area, buffer_m)
    if not isinstance(area, Polygon | MultiPolygon):
        raise AreaFileError("its shapes do not make an area")
    return area, found


def buffered(area: Any, buffer_m: float) -> Any:
    """``area`` (lon/lat) widened by ``buffer_m`` metres, measured on the ground."""
    frame = LocalFrame.for_polygon(area.convex_hull)
    inverse = Transformer.from_crs(frame.crs, "EPSG:4326", always_xy=True)
    forward = Transformer.from_crs("EPSG:4326", frame.crs, always_xy=True)

    def move(t: Transformer) -> Any:
        def apply(coords: Any) -> Any:
            xs, ys = t.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([xs, ys])

        return apply

    local = shapely.transform(area, move(forward))
    wide = local.buffer(buffer_m, join_style="mitre", mitre_limit=2.0)
    return shapely.transform(wide, move(inverse))
