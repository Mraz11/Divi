# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photo sequence: the first Lito X1 flight's faults rebuilt with fictional coordinates."""

from avispria.core.photo import PhotoRecord
from avispria.core.sequence import analyse_sequence, hover_repeats, split_runs
from photorecords import photo


def good_pass(start_i: int = 0, t0: float = 0.0, **kw: float) -> list[PhotoRecord]:
    return [photo(start_i + k, t0 + 2.0 * k, 10.0 * k, **kw) for k in range(20)]  # type: ignore[arg-type]


def test_a_clean_flight_has_no_findings() -> None:
    report = analyse_sequence(good_pass())
    assert report.issues == [] and report.leave_out == frozenset()
    assert len(report.runs) == 1 and report.runs[0].photos == 20
    assert report.median_interval_s == 2.0


def test_hovering_at_the_end_repeats_photos() -> None:
    photos = good_pass()
    last = photos[-1]
    end = [photo(100 + k, 40.0 + 6.5 * k, 190.0, speed=0.0) for k in range(5)]
    photos = [*photos[:-1], photo(19, 38.0, 190.0, speed=0.0), *end]
    report = analyse_sequence(photos)
    assert len(report.hover_repeats) == 5 and last.name not in report.hover_repeats
    assert [i.code for i in report.issues] == ["QA017"]
    assert hover_repeats(good_pass()) == []


def test_a_second_pass_over_the_same_ground_is_left_out() -> None:
    sharp = good_pass()
    blurred = good_pass(start_i=50, t0=200.0, exposure=1 / 100)
    report = analyse_sequence([*sharp, *blurred])
    assert len(split_runs(sorted([*sharp, *blurred], key=lambda r: r.time))) == 2  # type: ignore[arg-type, return-value]
    assert set(report.repeated_run) == {p.name for p in blurred}
    assert "QA018" in [i.code for i in report.issues]
    assert "QA020" in [i.code for i in report.issues]  # the slow pass is in the median


def test_a_resumed_flight_keeps_both_parts() -> None:
    first = good_pass()[:10]  # stopped halfway
    rest = [photo(60 + k, 300.0 + 2.0 * k, 90.0 + 10.0 * k) for k in range(11)]
    report = analyse_sequence([*first, *rest])
    assert len(report.runs) == 2 and report.repeated_run == ()


def test_a_slow_camera_and_a_slow_shutter() -> None:
    photos = [photo(k, 6.5 * k, 30.0 * k, exposure=1 / 40, width=8064) for k in range(10)]
    report = analyse_sequence(photos)
    codes = {i.code: i.message for i in report.issues}
    assert "12 MP" in codes["QA019"] and "6.5 s" in codes["QA019"]
    assert "1/40 s" in codes["QA020"]


def test_too_few_photos_or_no_times() -> None:
    assert analyse_sequence([]).runs == ()
    no_time = [photo(k, 0, 0) for k in range(3)]
    no_time = [
        PhotoRecord(**{**p.__dict__, "time": None})  # type: ignore[arg-type]
        for p in no_time
    ]
    assert analyse_sequence(no_time).issues == []
