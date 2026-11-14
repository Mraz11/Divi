# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the order and timing of the photos say about the flight.

Found in the first real flight with the Lito X1 (48 MP mode, automatic exposure):

* the camera could only take a photo every ~6.5 s, so photos fell between waypoints and the
  triggers that were still queued fired while the drone hovered at the last waypoint;
* DJI Fly's automatic exposure chose 1/180 s, five times longer than planned: blurred photos;
* the mission was flown twice, so every place was photographed twice.

Each finding becomes an issue, and the photos that only repeat others (taken while hovering, or
in a repeated pass) are named so processing can leave them out.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue

STILL_MS = 0.3  # slower than this the drone is hovering
SAME_PLACE_M = 2.0  # photos closer than this while hovering repeat each other
RUN_GAP_S = 60.0  # a pause this long between photos starts a new pass
SAME_GROUND_M = 8.0  # a photo this close to one of another pass covers the same ground
REPEAT_SHARE = 0.7  # this share of a pass on the same ground = a repeated pass
SLOW_CAMERA_S = 4.0  # moving photos further apart in time: the camera is the bottleneck
SLOW_SHUTTER_S = 1 / 400  # automatic exposure longer than this blurs a moving survey


@dataclass(frozen=True)
class Run:
    first: str
    last: str
    photos: int
    seconds: float
    median_blur_s: float | None  # speed x exposure: the motion during the exposure (m)


@dataclass(frozen=True)
class SequenceReport:
    runs: tuple[Run, ...]
    hover_repeats: tuple[str, ...]  # photos taken in the same place while hovering
    repeated_run: tuple[str, ...]  # photos of a pass that only repeats another
    median_interval_s: float | None  # between consecutive photos while moving
    median_exposure_s: float | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def leave_out(self) -> frozenset[str]:
        """Photos that add nothing: processing can skip them."""
        return frozenset((*self.hover_repeats, *self.repeated_run))


def _metres(a: PhotoRecord, b: PhotoRecord) -> float:
    assert a.lat is not None and a.lon is not None and b.lat is not None and b.lon is not None
    k = math.cos(math.radians((a.lat + b.lat) / 2))
    return math.hypot((a.lon - b.lon) * 111_320 * k, (a.lat - b.lat) * 110_574)


def _still(r: PhotoRecord) -> bool:
    return r.speed_ms is not None and r.speed_ms < STILL_MS


def hover_repeats(photos: Sequence[PhotoRecord]) -> list[str]:
    """Photos taken while hovering within SAME_PLACE_M of the photo before them."""
    out: list[str] = []
    for prev, cur in pairwise(photos):
        if _still(cur) and _still(prev) and _metres(prev, cur) < SAME_PLACE_M:
            out.append(cur.name)
    return out


def split_runs(photos: Sequence[PhotoRecord]) -> list[list[PhotoRecord]]:
    """Passes of the flight: photos with no pause longer than RUN_GAP_S between them."""
    runs: list[list[PhotoRecord]] = []
    for r in photos:
        prev = runs[-1][-1] if runs else None
        assert r.time is not None
        if prev is None or prev.time is None or (r.time - prev.time).total_seconds() > RUN_GAP_S:
            runs.append([])
        runs[-1].append(r)
    return runs


def _blur_m(run: Sequence[PhotoRecord]) -> float | None:
    values = [r.speed_ms * r.exposure_s for r in run if r.speed_ms is not None and r.exposure_s]
    return statistics.median(values) if values else None


def _same_ground(run: Sequence[PhotoRecord], other: Sequence[PhotoRecord]) -> float:
    near = sum(1 for r in run if any(_metres(r, o) < SAME_GROUND_M for o in other))
    return near / len(run)


def _repeated(runs: list[list[PhotoRecord]]) -> list[str]:
    """Photos of passes that cover the same ground as a sharper pass (the sharper one stays)."""

    def sharpness(i: int) -> tuple[float, int]:
        blur = _blur_m(runs[i])
        return (math.inf if blur is None else blur, -len(runs[i]))

    order = sorted(range(len(runs)), key=sharpness)
    kept: list[int] = []
    dropped: list[str] = []
    for i in order:
        if any(_same_ground(runs[i], runs[k]) >= REPEAT_SHARE for k in kept):
            dropped.extend(r.name for r in runs[i])
        else:
            kept.append(i)
    return dropped


def _interval(photos: Sequence[PhotoRecord]) -> float | None:
    gaps = [
        (b.time - a.time).total_seconds()
        for a, b in pairwise(photos)
        if a.time is not None and b.time is not None and not _still(a) and not _still(b)
    ]
    gaps = [g for g in gaps if 0 < g <= RUN_GAP_S]
    return statistics.median(gaps) if gaps else None


def analyse_sequence(records: Sequence[PhotoRecord]) -> SequenceReport:
    """Hovering repeats, repeated passes, camera rate and exposure, from the photos alone."""
    photos = sorted(
        (r for r in records if r.time is not None and r.lat is not None and r.lon is not None),
        key=lambda r: (r.time, r.name),
    )
    issues: list[Issue] = []
    if len(photos) < 2:
        return SequenceReport((), (), (), None, None, issues)
    runs = split_runs(photos)
    hover = hover_repeats(photos)
    repeated = [n for n in _repeated(runs) if n not in hover] if len(runs) > 1 else []
    interval = _interval(photos)
    exposures = [r.exposure_s for r in photos if r.exposure_s]
    exposure = statistics.median(exposures) if exposures else None
    if hover:
        issues.append(
            Issue(
                "warning",
                "QA017",
                f"{len(hover)} photo(s) taken while hovering in one place (left out of "
                "processing): the camera was still working through photo triggers when the drone "
                "stopped",
            )
        )
    if repeated:
        issues.append(
            Issue(
                "warning",
                "QA018",
                f"the flight has {len(runs)} passes over the same ground; the {len(repeated)} "
                "photos of the less sharp pass are left out of processing",
            )
        )
    sizes = [r.width_px * r.height_px for r in photos if r.width_px and r.height_px]
    megapixels = statistics.median(sizes) / 1e6 if sizes else 0.0
    if interval is not None and interval > SLOW_CAMERA_S:
        mode = " (48 MP photos: set DJI Fly's photo size to 12 MP)" if megapixels > 30 else ""
        issues.append(
            Issue(
                "warning",
                "QA019",
                f"the camera took a photo only every {interval:.1f} s while flying{mode}: photos "
                "fell between the waypoints instead of at them",
            )
        )
    if exposure is not None and exposure > SLOW_SHUTTER_S:
        issues.append(
            Issue(
                "warning",
                "QA020",
                f"the exposure was 1/{round(1 / exposure)} s (median): too long for a moving "
                "drone; set the camera to Pro (M) with a fast shutter (1/1000 s or faster)",
            )
        )
    found = tuple(
        Run(
            run[0].name,
            run[-1].name,
            len(run),
            (run[-1].time - run[0].time).total_seconds()  # type: ignore[operator]
            if len(run) > 1
            else 0.0,
            _blur_m(run),
        )
        for run in runs
    )
    return SequenceReport(found, tuple(hover), tuple(repeated), interval, exposure, issues)
