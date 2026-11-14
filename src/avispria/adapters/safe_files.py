# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading files that come from someone else (area files, archives) without trusting them.

* XML: no document type declarations, no entities, no network, no huge trees, so a crafted file
  cannot read local files, call out to the network or expand into gigabytes ("billion laughs").
* ZIP: a limit on the number of entries, on each entry and on the whole, checked while reading
  (the sizes in the archive's own directory can lie), and on how much an entry may expand, so a
  small "zip bomb" cannot fill the memory or the disk. Entry names that climb out of a folder
  are refused.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

MB = 1024 * 1024


class UnsafeFile(ValueError):
    """The file is refused; the message says why, in words a user can act on."""


@dataclass(frozen=True)
class Limits:
    entries: int = 64
    entry_bytes: int = 200 * MB
    total_bytes: int = 400 * MB
    ratio: float = 200.0  # how many times an entry may expand when unpacked
    file_bytes: int = 400 * MB  # the file itself, before opening it


AREA_LIMITS = Limits()


def check_size(path: Path, limits: Limits = AREA_LIMITS) -> None:
    size = path.stat().st_size
    if size > limits.file_bytes:
        raise UnsafeFile(
            f"{path.name} is {size / MB:.0f} MB; files over {limits.file_bytes / MB:.0f} MB are "
            "not read. Simplify the shapes or keep only the area you need."
        )


def safe_name(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    return not (name.startswith(("/", "\\")) or ".." in parts or ":" in name)


def checked_infos(archive: zipfile.ZipFile, limits: Limits = AREA_LIMITS) -> list[zipfile.ZipInfo]:
    """The archive's entries, after checking their number and names."""
    infos = archive.infolist()
    if len(infos) > limits.entries:
        raise UnsafeFile(f"the archive has {len(infos)} entries; at most {limits.entries} are read")
    for info in infos:
        if not safe_name(info.filename):
            raise UnsafeFile(f"the archive has an unsafe entry name: {info.filename!r}")
    return infos


def read_member(archive: zipfile.ZipFile, name: str, limits: Limits = AREA_LIMITS) -> bytes:
    """One entry's bytes, stopped as soon as it is bigger than allowed."""
    info = archive.getinfo(name)
    if not safe_name(info.filename):
        raise UnsafeFile(f"the archive has an unsafe entry name: {info.filename!r}")
    allowed = limits.entry_bytes
    if info.compress_size > 0:
        allowed = min(allowed, max(MB, int(info.compress_size * limits.ratio)))
    with archive.open(info) as handle:
        data = handle.read(allowed + 1)
    if len(data) > allowed:
        raise UnsafeFile(
            f"{info.filename} unpacks to more than {allowed / MB:.0f} MB: too big, or a file built "
            "to fill the memory (a zip bomb)"
        )
    return data


def read_members(
    archive: zipfile.ZipFile, names: list[str], limits: Limits = AREA_LIMITS
) -> dict[str, bytes]:
    """Several entries, with a limit on their total too."""
    checked_infos(archive, limits)
    found: dict[str, bytes] = {}
    total = 0
    for name in names:
        found[name] = read_member(archive, name, limits)
        total += len(found[name])
        if total > limits.total_bytes:
            raise UnsafeFile(f"the archive unpacks to more than {limits.total_bytes / MB:.0f} MB")
    return found


def parse_xml(data: bytes, label: str) -> etree._Element:
    """XML from someone else: no DOCTYPE, entities, network or huge trees; raises UnsafeFile."""
    if any(mark in data for mark in (b"<!DOCTYPE", b"<!doctype", b"<!ENTITY", b"<!entity")):
        raise UnsafeFile(f"{label}: document type declarations are not allowed")
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise UnsafeFile(f"{label}: it is not readable XML ({exc})") from None
