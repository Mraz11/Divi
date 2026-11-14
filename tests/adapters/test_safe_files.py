# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Files from someone else: zip bombs, entity tricks and climbing names are refused."""

import io
import zipfile
from pathlib import Path

import pytest

from avispria.adapters.area_file import AreaFileError, read_area_file
from avispria.adapters.safe_files import (
    MB,
    Limits,
    UnsafeFile,
    check_size,
    checked_infos,
    parse_xml,
    read_member,
    read_members,
    safe_name,
)

KML = (
    b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon>'
    b"<outerBoundaryIs><LinearRing><coordinates>0,0 0.001,0 0.001,0.001 0,0</coordinates>"
    b"</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"
)
LAUGHS = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
    b"<kml>&lol2;</kml>"
)
SECRET = (
    b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY s SYSTEM "file:///etc/passwd">]><kml>&s;</kml>'
)


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def test_xml_with_declarations_or_entities_is_refused() -> None:
    assert parse_xml(KML, "area").tag.endswith("kml")
    for data in (LAUGHS, SECRET, b"<kml><!ENTITY x 'y'></kml>"):
        with pytest.raises(UnsafeFile, match="not allowed"):
            parse_xml(data, "area")
    with pytest.raises(UnsafeFile, match="not readable XML"):
        parse_xml(b"<kml>", "area")


def test_a_zip_bomb_is_stopped_while_reading() -> None:
    bomb = _zip({"doc.kml": b"\0" * (12 * MB)})  # 12 MB of zeros packs to a few kB
    assert len(bomb) < 100_000
    with zipfile.ZipFile(io.BytesIO(bomb)) as archive, pytest.raises(UnsafeFile, match="zip bomb"):
        read_member(archive, "doc.kml")
    small = Limits(entries=2, entry_bytes=10, total_bytes=15, ratio=1e9)
    with zipfile.ZipFile(io.BytesIO(_zip({"a": b"x" * 8, "b": b"y" * 8}))) as archive:
        assert read_member(archive, "a", small) == b"x" * 8
        with pytest.raises(UnsafeFile, match="more than 0 MB"):
            read_members(archive, ["a", "b"], small)
    three = io.BytesIO(_zip({str(n): b"" for n in range(3)}))
    with zipfile.ZipFile(three) as archive, pytest.raises(UnsafeFile, match="3 entries"):
        checked_infos(archive, small)


def test_names_that_climb_out_are_refused() -> None:
    assert safe_name("wpmz/template.kml") and safe_name("a/b.shp")
    for name in ("../evil.kml", "/etc/passwd", "C:/x.kml", "a/../../b", "..\\x"):
        assert not safe_name(name), name
    with zipfile.ZipFile(io.BytesIO(_zip({"../x.kml": KML}))) as archive:
        with pytest.raises(UnsafeFile, match="unsafe entry name"):
            checked_infos(archive)
        with pytest.raises(UnsafeFile, match="unsafe entry name"):
            read_member(archive, "../x.kml")


def test_area_files_that_attack_are_refused_with_a_reason(tmp_path: Path) -> None:
    good = tmp_path / "area.kml"
    good.write_bytes(KML)
    assert read_area_file(good).polygons
    for name, data, message in (
        ("laughs.kml", LAUGHS, "not allowed"),
        ("secret.kml", SECRET, "not allowed"),
        ("bomb.kmz", _zip({"doc.kml": b"<kml>" + b" " * (12 * MB) + b"</kml>"}), "zip bomb"),
        ("climb.zip", _zip({"../area.shp": b"x"}), "unsafe entry name"),
    ):
        path = tmp_path / name
        path.write_bytes(data)
        with pytest.raises(AreaFileError, match=message):
            read_area_file(path)


def test_files_too_big_to_open_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "huge.geojson"
    path.write_bytes(b"{}" * 10)
    check_size(path)
    with pytest.raises(UnsafeFile, match="not read"):
        check_size(path, Limits(file_bytes=5))
