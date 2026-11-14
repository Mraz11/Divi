# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.analyses import KEYS, SWITCHES, SwitchError, checked, describe, on, trim_metrics


def test_every_analysis_can_be_named_and_is_described() -> None:
    assert KEYS == (
        "landcover",
        "buildings",
        "roads",
        "street_shade",
        "rule_3_30_300",
        "heat",
        "biomass",
        "indices",
        "symptoms",
    )
    assert all(s.title and s.what.endswith(".") for s in SWITCHES)


def test_switches_are_checked_and_kept_in_order() -> None:
    assert checked(["symptoms", "landcover", "landcover"]) == ("landcover", "symptoms")
    with pytest.raises(SwitchError, match="no analysis called lidar"):
        checked(["lidar"])
    assert on("roads", ()) and not on("roads", ["roads"])
    assert describe(()) == "all analyses on"
    assert describe(["biomass"]) == "switched off: Biomass and carbon"


def test_switched_off_metrics_are_left_out() -> None:
    metrics = {"tree_canopy_pct": 40, "green_pct": 50, "roads": 2, "canopy_30_rule_met": True}
    assert trim_metrics(metrics, ["landcover", "rule_3_30_300"]) == {
        "tree_canopy_pct": 40,
        "roads": 2,
    }
    assert trim_metrics(metrics, ()) == metrics
