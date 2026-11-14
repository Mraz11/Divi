# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain-language explanations for mission-file (WPML) and canopy codes; see ``explain``."""

from __future__ import annotations

from avispria.app.ui.explain_base import Explanation, _e

_FILE = "Re-create the file with Dīvi from your own DJI Fly mission file. If it keeps failing, send the file to the developers."

MORE: dict[str, Explanation] = {
    # ---- mission-file checks
    "WPML001": _e(
        "Not a valid mission file", "The file could not be read as a DJI Fly mission.", _FILE
    ),
    "WPML002": _e(
        "Mission file parts do not match", "The two parts of the file use different formats.", _FILE
    ),
    "WPML003": _e(
        "Not the DJI Fly format",
        "The file uses a format other than DJI Fly's, so DJI Fly may not open it.",
        "Create the file from your own DJI Fly sample mission.",
    ),
    "WPML004": _e(
        "Heights are not relative to takeoff",
        "The file measures heights in a way DJI Fly consumer drones do not support.",
        _FILE,
    ),
    "WPML005": _e("Fewer than two waypoints", "A mission needs at least two waypoints.", _FILE),
    "WPML006": _e(
        "Waypoint numbering is wrong",
        "The waypoints are not numbered 0, 1, 2, ... in order.",
        _FILE,
    ),
    "WPML007": _e(
        "Invalid coordinates", "A waypoint has a latitude or longitude that is not valid.", _FILE
    ),
    "WPML008": _e("Height out of range", "A waypoint height is not a sensible number.", _FILE),
    "WPML009": _e(
        "Speed out of range",
        "A speed in the file is zero, negative or above what the aircraft can do.",
        _FILE,
    ),
    "WPML010": _e("Too many waypoints", "The file has more waypoints than the limit.", _FILE),
    "WPML011": _e(
        "Two waypoints at the same place",
        "Two neighbouring waypoints are almost on top of each other.",
        _FILE,
    ),
    "WPML012": _e(
        "Very long straight leg",
        "One leg between two waypoints is unusually long.",
        "Check that this is intended, and that the drone stays in sight.",
    ),
    "WPML013": _e(
        "Camera angle out of range",
        "A waypoint asks for a camera angle the gimbal cannot reach.",
        _FILE,
    ),
    "WPML014": _e(
        "Camera action on the wrong waypoint",
        "An action in the file refers to a waypoint it does not belong to.",
        _FILE,
    ),
    "WPML015": _e("Duplicate action numbers", "Two actions share the same ID.", _FILE),
    "WPML016": _e(
        "Unusual finish or signal-lost behaviour",
        "The aircraft would not return home when the mission ends or the signal is lost, as DJI Fly normally sets it.",
        "Check this is what you want before flying.",
    ),
    # ---- planning
    "PL004": _e(
        "Split by the waypoint limit, not the battery",
        "DJI Fly takes a limited number of waypoints per mission, and a photo at every waypoint uses many of them, so the plan needs more than one mission even though the flight is short.",
        "Fly the missions one after another on the same battery: start the next one as soon as the drone is back. Raise 'Waypoints per mission' in Advanced only after one test shows DJI Fly accepts more.",
    ),
    # ---- the order and timing of the photos
    "QA017": _e(
        "Photos taken while hovering",
        "Several photos were taken in the same place while the drone stood still, usually at the last waypoint: the camera was still working through photo triggers it could not keep up with. They add nothing and are left out of processing.",
        "Set DJI Fly's photo size to 12 MP (48 MP photos take about 6.5 s each) and plan again if you changed the camera mode.",
    ),
    "QA018": _e(
        "The same ground was flown twice",
        "The photos form two or more passes over the same ground, for example because the mission was started again. Dīvi keeps the sharper pass and leaves the other out, so processing does not take twice as long or mix two lights.",
        "Nothing to do. To use every photo, tick 'Use every photo' on Make maps (or pass --keep-repeats).",
    ),
    "QA019": _e(
        "The camera could not keep up",
        "While flying, the camera took a photo only every few seconds, slower than the plan asked for, so photos fell between waypoints and some were never taken.",
        "Set DJI Fly's photo size to 12 MP. For 48 MP, plan with the 48 MP camera mode, which flies slower.",
    ),
    "QA020": _e(
        "Shutter too slow for a moving drone",
        "DJI Fly's automatic exposure chose a long exposure time, so the drone moved several pixels while each photo was taken: blurred photos.",
        "Before the flight switch the camera to Pro (M), set the shutter to 1/1000 s (1/500 s in poor light) and ISO to Auto, or fly in brighter light.",
    ),
    "QA021": _e(
        "Low sun",
        "The photos were taken with the sun low in the sky. Shadows many times longer than the trees hide the ground and the gaps, the camera needs slow shutters (blur), and the light is orange. Canopy heights and colour measures from such a flight are less reliable, and flights at different sun heights cannot be compared fairly.",
        "Fly when the sun is at least 35 degrees up: the Plan screen shows today's window for your area (in the tropics in winter, about 09:30 to 14:00).",
    ),
    # ---- canopy height
    "CH001": _e(
        "Ground hardly seen",
        "The canopy is so closed that the ground showed in very few places, so canopy heights rest on a guessed ground.",
        "Fly in leaf-off season, include some open ground in the area, or use a ground model from LiDAR.",
    ),
    "CH002": _e(
        "Ground estimated from the surface",
        "The engine made no ground model, so Dīvi estimated the ground from the surface model itself; heights are approximate.",
        "Process with the Standard or Detailed preset, and check a few tree heights in the field.",
    ),
    "LC001": _e(
        "Land cover uncertain",
        "Over much of the map the land cover rests on weak evidence: colours inside shadows, colours in low sun, a ground that was estimated, or heights close to a class limit. confidence.tif shows where.",
        "Fly between mid-morning and early afternoon, process with Standard or Detailed (which makes a ground model), and check a sample of the land cover against the orthophoto.",
    ),
    "CH003": _e(
        "Crown colours not trustworthy",
        "With the sun this low, orange light and long shadows change the colour of healthy crowns, so the dieback candidates may be wrong in both directions.",
        "Use the crown outlines and heights, but judge crown condition from a flight between mid-morning and early afternoon.",
    ),
}
