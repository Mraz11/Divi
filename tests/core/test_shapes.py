# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import math
import random

import pytest
from shapely.geometry import Polygon

from avispria.core.geometry import rectangle_polygon
from avispria.core.shapes import (
    DEFAULT_WIDTH_M,
    DrawnShape,
    Role,
    ShapeError,
    build_area,
    shape_size,
    suggest_role,
)

LAT, LON = 51.4769, -0.0015


def rect(
    i: int,
    width: float,
    length: float,
    dx: float = 0.0,
    dy: float = 0.0,
    role: Role = Role.INSIDE,
    **kw: float,
) -> DrawnShape:
    """A rectangle ``width`` x ``length`` metres, its centre moved dx metres east and dy north."""
    dlat = dy / 111_320.0
    dlon = dx / (111_320.0 * math.cos(math.radians(LAT)))
    ring = rectangle_polygon(LAT + dlat, LON + dlon, width, length, 0.0).exterior.coords
    return DrawnShape(i, "rectangle", tuple((x, y) for x, y in list(ring)[:4]), role=role, **kw)


def line(i: int, length: float, width: float = 20.0) -> DrawnShape:
    dlon = length / (111_320.0 * math.cos(math.radians(LAT)))
    return DrawnShape(i, "line", ((LON, LAT), (LON + dlon, LAT)), role=Role.CORRIDOR, width_m=width)


def circle(i: int, radius: float, role: Role = Role.INSIDE) -> DrawnShape:
    return DrawnShape(i, "circle", ((LON, LAT),), radius_m=radius, role=role)


def total(result) -> float:  # type: ignore[no-untyped-def]
    return sum(p.area_m2 for p in result.pieces)


def test_one_rectangle_is_that_area() -> None:
    result = build_area([rect(1, 100, 100)])
    assert len(result.pieces) == 1 and result.pieces[0].area_m2 == pytest.approx(10_000, rel=0.01)
    assert result.pieces[0].polygon.centroid.x == pytest.approx(LON, abs=1e-4)
    assert result.pieces[0].polygon.centroid.y == pytest.approx(LAT, abs=1e-4)  # back in lon/lat


def test_a_shape_inside_another_can_be_left_out_and_becomes_a_hole() -> None:
    result = build_area([rect(1, 200, 200), rect(2, 50, 50, role=Role.LEAVE_OUT)])
    (piece,) = result.pieces
    assert piece.area_m2 == pytest.approx(40_000 - 2_500, rel=0.01)
    assert len(piece.polygon.interiors) == 1  # the planner takes one polygon, with a hole


def test_leaving_out_a_strip_across_the_area_makes_two_pieces_largest_first() -> None:
    cut = rect(2, 400, 20, dx=0, dy=40, role=Role.LEAVE_OUT)  # a road 40 m north of the centre
    result = build_area([rect(1, 200, 200), cut])
    assert len(result.pieces) == 2
    assert result.pieces[0].area_m2 > result.pieces[1].area_m2
    assert total(result) == pytest.approx(200 * 200 - 200 * 20, rel=0.01)


def test_a_band_maps_the_outside_of_a_shape_and_not_the_shape_itself() -> None:
    """'Map the outside of the polygon': a ring of 30 m around a 50 m building."""
    result = build_area([rect(1, 50, 50, role=Role.BAND, width_m=30.0)])
    (piece,) = result.pieces
    # the outer outline has rounded corners: (50 + 60)^2 minus the cut corners, minus the building
    expected = (50 + 60) ** 2 - (4 - math.pi) * 30**2 - 50 * 50
    assert piece.area_m2 == pytest.approx(expected, rel=0.01)
    assert len(piece.polygon.interiors) == 1  # the building is the hole


def test_a_line_becomes_a_strip_of_its_width() -> None:
    result = build_area([line(1, 200.0, width=20.0)])
    assert total(result) == pytest.approx(200 * 20, rel=0.01)


def test_a_circle_is_a_round_area() -> None:
    assert total(build_area([circle(1, 40)])) == pytest.approx(math.pi * 40**2, rel=0.01)


def test_a_circle_can_be_left_out_of_a_rectangle() -> None:
    result = build_area([rect(1, 200, 200), circle(2, 30, role=Role.LEAVE_OUT)])
    assert total(result) == pytest.approx(40_000 - math.pi * 30**2, rel=0.01)


def test_a_leave_out_also_cuts_a_corridor() -> None:
    result = build_area([line(1, 200.0, width=20.0), rect(2, 40, 100, dx=100, role=Role.LEAVE_OUT)])
    assert len(result.pieces) == 2  # the line is cut in two by a gap in the middle


def test_the_order_in_which_shapes_were_drawn_does_not_matter() -> None:
    shapes = [
        rect(1, 200, 200),
        rect(2, 50, 50, role=Role.LEAVE_OUT),
        line(3, 150.0),
        circle(4, 25),
    ]
    reference = total(build_area(shapes))
    rng = random.Random(3)
    for _ in range(6):
        rng.shuffle(shapes)
        assert total(build_area(shapes)) == pytest.approx(reference, rel=1e-9)


def test_pieces_too_small_to_fly_are_dropped_and_reported() -> None:
    result = build_area([rect(1, 100, 100), rect(2, 6, 6, dx=300)])  # a 36 m2 speck far away
    assert len(result.pieces) == 1 and result.dropped_m2 == pytest.approx(36, rel=0.05)


@pytest.mark.parametrize(
    ("shapes", "message"),
    [
        ([], "Draw at least one shape"),
        ([rect(1, 100, 100, role=Role.LEAVE_OUT)], "Nothing is set to be mapped"),
        (
            [rect(1, 50, 50), rect(2, 200, 200, role=Role.LEAVE_OUT)],
            "cut away by the parts you left out",
        ),
        ([rect(1, 5, 5)], "too small"),
        ([line(1, 100.0, width=0.0)], "width must be between"),
        ([line(1, 100.0, width=5000.0)], "width must be between"),
        ([rect(1, 50, 50, role=Role.BAND, width_m=0.0)], "width must be between"),
        (
            [DrawnShape(1, "line", ((LON, LAT), (LON, LAT)), role=Role.CORRIDOR)],
            "two different points",
        ),
        (
            [DrawnShape(1, "line", ((LON, LAT), (LON + 0.001, LAT)), role=Role.INSIDE)],
            "cannot be set to",
        ),
        (
            [DrawnShape(1, "polygon", ((LON, LAT), (LON + 0.001, LAT)), role=Role.INSIDE)],
            "at least three",
        ),
        ([DrawnShape(1, "circle", ((LON, LAT),), radius_m=0.0)], "needs a centre and a radius"),
        (
            [DrawnShape(1, "polygon", ((LON, 95.0), (LON, 94.0), (LON + 0.1, 94.5)))],
            "coordinates are not valid",
        ),
        ([DrawnShape(1, "hexagon", ((LON, LAT),))], "unknown kind"),
        (  # a bow tie: the outline crosses itself
            [
                DrawnShape(
                    1,
                    "polygon",
                    (
                        (LON, LAT),
                        (LON + 0.001, LAT + 0.001),
                        (LON + 0.001, LAT),
                        (LON, LAT + 0.001),
                    ),
                )
            ],
            "crosses itself",
        ),
    ],
)
def test_shapes_that_cannot_make_an_area_say_what_to_change(shapes: list, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ShapeError, match=message):
        build_area(shapes)


def test_the_result_is_something_the_planner_accepts() -> None:
    from shapely.geometry import mapping

    from avispria.core.geometry import load_aoi

    result = build_area([rect(1, 200, 200), rect(2, 50, 50, role=Role.LEAVE_OUT)])
    again = load_aoi(mapping(result.pieces[0].polygon))
    assert isinstance(again, Polygon) and len(again.interiors) == 1


def test_a_sensible_first_role_for_each_new_shape() -> None:
    big = rect(1, 200, 200)
    assert suggest_role(big, []) == Role.INSIDE  # the first area is mapped
    assert (
        suggest_role(rect(2, 50, 50), [big]) == Role.LEAVE_OUT
    )  # drawn inside it: a part to leave out
    assert (
        suggest_role(rect(3, 50, 50, dx=500), [big]) == Role.INSIDE
    )  # somewhere else: another area
    assert (
        suggest_role(rect(4, 300, 300), [big]) == Role.INSIDE
    )  # bigger, so it does not fit inside
    assert suggest_role(line(5, 100.0), [big]) == Role.CORRIDOR
    assert suggest_role(rect(6, 50, 50), [rect(7, 100, 100, role=Role.LEAVE_OUT)]) == Role.INSIDE


def test_the_size_shown_beside_a_shape() -> None:
    value, unit = shape_size(rect(1, 100, 60))
    assert unit == "m2" and value == pytest.approx(6_000, rel=0.01)
    value, unit = shape_size(line(2, 250.0))
    assert unit == "m" and value == pytest.approx(250, rel=0.01)
    assert DEFAULT_WIDTH_M == 30.0


# ------------------------------------------------------------------------------ editing a shape
from avispria.core.shapes import reshape, with_radius  # noqa: E402


def moved(points: tuple, index: int, lon: float, lat: float) -> tuple:  # type: ignore[type-arg]
    out = list(points)
    out[index] = (lon, lat)
    return tuple(out)


def test_dragging_a_corner_changes_only_that_corner_and_the_area() -> None:
    square = rect(1, 100, 100, role=Role.LEAVE_OUT)
    corner = square.points[2]
    dragged = reshape(square, moved(square.points, 2, corner[0] + 0.0005, corner[1]))
    assert dragged.points[2][0] == pytest.approx(corner[0] + 0.0005)
    assert total(build_area([rect(9, 300, 300), dragged])) < total(
        build_area([rect(9, 300, 300), square])
    )
    assert (dragged.id, dragged.role, dragged.width_m) == (square.id, square.role, square.width_m)
    assert dragged.kind == "polygon"  # a rectangle whose corner moved: its role still applies


def test_an_unchanged_rectangle_stays_a_rectangle_and_a_closed_ring_is_understood() -> None:
    square = rect(1, 100, 100)
    assert reshape(square, square.points).kind == "rectangle"
    ring = (*square.points, square.points[0])  # how a map hands back an outline
    assert reshape(square, ring).points == square.points


def test_corners_can_be_added_and_removed_but_an_area_keeps_three_and_a_line_two() -> None:
    four = rect(1, 100, 100)
    a, b = four.points[0], four.points[1]
    five = reshape(four, (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), *four.points[1:]))
    assert len(five.points) == 5
    assert total(build_area([five])) == pytest.approx(total(build_area([four])), rel=0.001)
    assert len(reshape(four, four.points[:3]).points) == 3
    with pytest.raises(ShapeError, match="at least 3 corners"):
        reshape(four, four.points[:2])
    with pytest.raises(ShapeError, match="at least 2 corners"):
        reshape(line(2, 100.0), line(2, 100.0).points[:1])


def test_a_circle_moves_by_its_centre_and_its_radius_follows_the_handle() -> None:
    dragged = reshape(circle(1, 40), ((LON + 0.001, LAT),), 65.0)
    assert dragged.kind == "circle" and dragged.radius_m == 65.0
    assert dragged.points == ((LON + 0.001, LAT),)
    assert reshape(circle(1, 40), ((LON, LAT),)).radius_m == 40  # radius kept when not given
    with pytest.raises(ShapeError, match="one centre"):
        reshape(circle(1, 40), ((LON, LAT), (LON, LAT)))


def test_a_corner_dragged_to_make_the_outline_cross_itself_is_refused() -> None:
    square = rect(1, 100, 100)
    p0, p1, p2, _ = square.points
    # past the side p1-p2, level with its middle: the side p3-p0 now cuts across it (a bow tie)
    far = (
        p1[0] + (p1[0] - p0[0]) + (p2[0] - p1[0]) / 2,
        p1[1] + (p1[1] - p0[1]) + (p2[1] - p1[1]) / 2,
    )
    with pytest.raises(ShapeError, match="crosses itself"):
        reshape(square, moved(square.points, 0, far[0], far[1]))
    with pytest.raises(ShapeError, match="not valid"):
        reshape(square, moved(square.points, 0, 500.0, 0.0))


def test_a_circles_radius_can_change_but_not_to_nothing() -> None:
    assert with_radius(circle(1, 40), 55).radius_m == 55
    for bad in (0.0, -5.0, float("nan")):
        with pytest.raises(ShapeError, match="needs a centre and a radius"):
            with_radius(circle(1, 40), bad)
    with pytest.raises(ShapeError, match="Only a circle"):
        with_radius(rect(1, 10, 10), 5)
