"""The market projections as they reach the bundle.

The payload already carries a 1X2 split and the full grid. Adding a markets
block introduces one specific hazard: a SECOND representation of a number the
payload already states. If the two ever disagree, the bundle contradicts
itself and both numbers become unusable — so the equality is pinned here
rather than assumed from the fact that they happen to share a code path
today.

The gate tests are the other half. A market block that does not sum to 1 is
not a rounding annoyance; it is a probability claim that cannot be true, and
the bundle's whole contract is that a naked or incoherent artifact is never
written. So the gate must STOP on it, exactly as it does for the 1X2 and the
cover pair.
"""
import numpy as np
import pytest

from wcmodel.dashboard.fixtures import fixture_forecast
from wcmodel.dashboard.schema import gate_fixture_forecast
from wcmodel.model import markets as mk


class _FakePost:
    """Grid-fixed posterior. Its 1X2 is stated independently of its grid so a
    reconciliation bug cannot hide behind a shared computation."""
    teams = ["Spain", "Morocco"]

    def predict_scoreline(self, home, away, neutral=False, max_goals=10,
                          covariates=None, host_factor=None):
        g = np.zeros((4, 4))
        g[1, 0] = 0.5      # home win, home clean sheet, 1 goal
        g[2, 1] = 0.3      # home win, BTTS, 3 goals
        g[0, 0] = 0.2      # draw, both clean sheets, 0 goals
        return g

    def predict_1x2(self, home, away, neutral=False, max_goals=10,
                    covariates=None, host_factor=None):
        return {"home": 0.8, "draw": 0.2, "away": 0.0}


def _forecast():
    return fixture_forecast(_FakePost(), home="Spain", away="Morocco",
                            neutral=True, max_goals=3)


# ------------------------------------------------------- presence + identity
def test_forecast_carries_a_markets_block():
    m = _forecast()["markets"]
    assert set(m) >= {"one_x_two", "double_chance", "over_under",
                      "both_teams_to_score", "clean_sheet", "correct_score"}


def test_markets_1x2_is_identical_to_the_payloads_own_1x2():
    """Two representations of one number must never drift apart. This is the
    regression guard: change one source without the other and this fails."""
    f = _forecast()
    assert f["markets"]["one_x_two"] == f["one_x_two"]


def test_markets_agree_with_the_grid_the_payload_publishes():
    """Stronger than the above: the markets must be a projection of the grid
    that actually ships, not of some other grid computed alongside it."""
    f = _forecast()
    grid = np.array(f["grid"])
    assert f["markets"]["both_teams_to_score"] == mk.both_teams_to_score(grid)
    assert f["markets"]["clean_sheet"] == mk.clean_sheet(grid)


def test_markets_read_the_grid_the_right_way_round():
    """Home keeps a clean sheet when AWAY fails to score: (1,0) and (0,0)."""
    m = _forecast()["markets"]
    assert m["clean_sheet"]["home"] == pytest.approx(0.7)
    assert m["clean_sheet"]["away"] == pytest.approx(0.2)
    assert m["both_teams_to_score"]["yes"] == pytest.approx(0.3)


def test_markets_are_json_safe():
    """The bundle is written to JSON; numpy scalars are not serialisable."""
    import json
    json.dumps(_forecast()["markets"])


# ----------------------------------------------------------------- the gate
def _valid_markets():
    return _forecast()["markets"]


def _forecast_with(markets):
    f = _forecast()
    f["markets"] = markets
    return f


def test_gate_accepts_a_coherent_markets_block():
    gate_fixture_forecast(_forecast())


def test_gate_accepts_a_forecast_with_no_markets_block():
    """A forecast built before this feature must still gate clean — the same
    optionality the cover pair has."""
    f = _forecast()
    del f["markets"]
    gate_fixture_forecast(f)


def test_gate_stops_an_over_under_that_does_not_sum_to_one():
    m = _valid_markets()
    m["over_under"]["2.5"] = {"over": 0.4, "under": 0.4, "push": 0.0}
    with pytest.raises(ValueError, match="sum to ~1"):
        gate_fixture_forecast(_forecast_with(m))


def test_gate_stops_a_btts_that_does_not_sum_to_one():
    m = _valid_markets()
    m["both_teams_to_score"] = {"yes": 0.6, "no": 0.6}
    with pytest.raises(ValueError, match="sum to ~1"):
        gate_fixture_forecast(_forecast_with(m))


def test_gate_stops_a_probability_outside_the_unit_interval():
    m = _valid_markets()
    m["both_teams_to_score"] = {"yes": 1.4, "no": -0.4}
    with pytest.raises(ValueError, match=r"\[0, ?1\]"):
        gate_fixture_forecast(_forecast_with(m))


def test_gate_stops_a_double_chance_leg_outside_the_unit_interval():
    """Double chance legitimately does NOT sum to 1 (each pair double-counts),
    so it is value-checked rather than sum-checked — and that must still be a
    real check, not a skipped one."""
    m = _valid_markets()
    m["double_chance"]["home_or_draw"] = 1.7
    with pytest.raises(ValueError, match=r"\[0, ?1\]"):
        gate_fixture_forecast(_forecast_with(m))


def test_gate_stops_a_clean_sheet_side_outside_the_unit_interval():
    """Clean sheet is per side and does NOT sum to 1 (both sides can keep one
    in a 0-0), so it too is value-checked, never sum-checked."""
    m = _valid_markets()
    m["clean_sheet"]["away"] = float("nan")
    with pytest.raises(ValueError, match=r"\[0, ?1\]"):
        gate_fixture_forecast(_forecast_with(m))


def test_gate_stops_a_correct_score_entry_without_a_real_probability():
    m = _valid_markets()
    m["correct_score"][0] = {"home": 1, "away": 0}
    with pytest.raises(ValueError, match="correct score"):
        gate_fixture_forecast(_forecast_with(m))


def test_gate_stops_a_markets_block_that_is_not_a_mapping():
    with pytest.raises(ValueError, match="markets"):
        gate_fixture_forecast(_forecast_with([1, 2, 3]))
