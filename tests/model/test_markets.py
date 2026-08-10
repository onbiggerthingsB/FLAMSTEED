"""Tests for the market projections of a scoreline grid.

Every market here is a DIFFERENT VIEW of one object the model already
produces. That makes the failure mode specific: not "the model is wrong" but
"this projection reads the grid the wrong way round", which is silent and
produces perfectly plausible numbers. So the tests below are mostly about
orientation, exhaustiveness, and refusing a grid that cannot be a probability
distribution.

The 1X2 projection is NOT re-implemented — it delegates to the production
``grid_one_x_two``, and a test pins that delegation, because two copies of
the home/away convention is exactly how a flip ships unnoticed.
"""
import numpy as np
import pytest

from wcmodel.model.draw_api import grid_one_x_two
from wcmodel.model.markets import (
    MarketError,
    both_teams_to_score,
    clean_sheet,
    correct_score,
    double_chance,
    one_x_two,
    over_under,
    project_all,
)


def _grid(pairs, size=6):
    """Build a normalised grid from {(home_goals, away_goals): prob}."""
    g = np.zeros((size, size))
    for (h, a), p in pairs.items():
        g[h, a] = p
    return g


@pytest.fixture
def asymmetric():
    """Deliberately lopsided toward the HOME side, so any transpose shows up."""
    return _grid({
        (2, 0): 0.30,   # home win, clean sheet for home, under 2.5, no BTTS
        (1, 0): 0.20,   # home win, clean sheet for home, under 2.5, no BTTS
        (1, 1): 0.15,   # draw, BTTS, under 2.5
        (2, 1): 0.15,   # home win, BTTS, over 2.5
        (0, 1): 0.10,   # away win, clean sheet for away, under 2.5, no BTTS
        (3, 2): 0.10,   # home win, BTTS, over 2.5
    })


# ------------------------------------------------------- input validation
def test_a_grid_that_is_not_a_distribution_is_refused():
    """Projecting an unnormalised grid yields probabilities that look fine and
    are wrong. Refuse loudly instead."""
    with pytest.raises(MarketError, match="sum to 1"):
        one_x_two(_grid({(1, 0): 0.5, (0, 1): 0.2}))


def test_a_negative_cell_is_refused():
    g = _grid({(1, 0): 1.2, (0, 1): -0.2})
    with pytest.raises(MarketError, match="negative"):
        one_x_two(g)


def test_a_non_square_grid_is_refused():
    with pytest.raises(MarketError, match="square"):
        one_x_two(np.ones((3, 4)) / 12)


# ------------------------------------------------------------- 1X2 + DC
def test_one_x_two_delegates_to_the_production_projection(asymmetric):
    """One home/away convention in the codebase, not two."""
    assert one_x_two(asymmetric) == grid_one_x_two(asymmetric)


def test_one_x_two_orientation_is_home_rows(asymmetric):
    # home wins: (2,0) (1,0) (2,1) (3,2) = .30+.20+.15+.10
    assert one_x_two(asymmetric)["home"] == pytest.approx(0.75)
    assert one_x_two(asymmetric)["draw"] == pytest.approx(0.15)
    assert one_x_two(asymmetric)["away"] == pytest.approx(0.10)


def test_double_chance_is_exactly_the_sum_of_its_two_legs(asymmetric):
    dc, r = double_chance(asymmetric), one_x_two(asymmetric)
    assert dc["home_or_draw"] == pytest.approx(r["home"] + r["draw"])
    assert dc["home_or_away"] == pytest.approx(r["home"] + r["away"])
    assert dc["draw_or_away"] == pytest.approx(r["draw"] + r["away"])


# -------------------------------------------------------- over / under
def test_half_line_splits_cleanly_with_no_push(asymmetric):
    ou = over_under(asymmetric, 2.5)
    # totals: 2,1,2,3,1,5 -> over 2.5 is (2,1)=.15 and (3,2)=.10
    assert ou["over"] == pytest.approx(0.25)
    assert ou["under"] == pytest.approx(0.75)
    assert ou["push"] == 0.0
    assert ou["over"] + ou["under"] + ou["push"] == pytest.approx(1.0)


def test_integer_line_reports_a_real_push(asymmetric):
    """A 2.0 line is a push when exactly two goals are scored. Folding that
    into over or under would misprice the market and quietly break the sum."""
    ou = over_under(asymmetric, 2.0)
    assert ou["push"] == pytest.approx(0.45)      # (2,0) and (1,1)
    assert ou["over"] == pytest.approx(0.25)      # totals 3 and 5
    assert ou["under"] == pytest.approx(0.30)     # totals 1 and 1
    assert ou["over"] + ou["under"] + ou["push"] == pytest.approx(1.0)


@pytest.mark.parametrize("line", [0.5, 1.5, 2.5, 3.5, 4.5])
def test_over_is_monotone_decreasing_in_the_line(asymmetric, line):
    """P(over L) must never rise as L rises — the single cheapest check that
    the comparison is the right way round."""
    assert over_under(asymmetric, line)["over"] >= \
        over_under(asymmetric, line + 1)["over"]


def test_a_negative_line_is_refused(asymmetric):
    with pytest.raises(MarketError, match="line"):
        over_under(asymmetric, -0.5)


# ------------------------------------------------ BTTS / clean sheet
def test_btts_requires_both_sides_to_score(asymmetric):
    b = both_teams_to_score(asymmetric)
    assert b["yes"] == pytest.approx(0.40)        # (1,1) (2,1) (3,2)
    assert b["no"] == pytest.approx(0.60)
    assert b["yes"] + b["no"] == pytest.approx(1.0)


def test_clean_sheet_is_per_side_and_not_transposed(asymmetric):
    cs = clean_sheet(asymmetric)
    # home keeps a clean sheet when AWAY scores 0: (2,0) (1,0) = .50
    assert cs["home"] == pytest.approx(0.50)
    # away keeps a clean sheet when HOME scores 0: (0,1) = .10
    assert cs["away"] == pytest.approx(0.10)


# ------------------------------------------------------- correct score
def test_correct_score_is_ranked_and_reads_real_cells(asymmetric):
    top = correct_score(asymmetric, top_n=3)
    assert [(s["home"], s["away"]) for s in top] == [(2, 0), (1, 0), (1, 1)]
    assert top[0]["prob"] == pytest.approx(0.30)
    assert all(top[i]["prob"] >= top[i + 1]["prob"] for i in range(len(top) - 1))


def test_correct_score_ties_break_deterministically():
    """Equal cells must not reorder between runs, or a published shortlist
    changes on a rerun with identical inputs."""
    g = _grid({(1, 0): 0.5, (0, 1): 0.5})
    assert correct_score(g, top_n=2) == correct_score(g, top_n=2)


# -------------------------------------------------------------- bundle
def test_project_all_covers_every_market_and_each_sums_to_one(asymmetric):
    out = project_all(asymmetric)
    assert set(out) >= {"one_x_two", "double_chance", "over_under",
                        "both_teams_to_score", "clean_sheet", "correct_score"}
    assert sum(out["one_x_two"].values()) == pytest.approx(1.0)
    assert sum(out["both_teams_to_score"].values()) == pytest.approx(1.0)
    for line, ou in out["over_under"].items():
        assert sum(ou.values()) == pytest.approx(1.0), f"line {line}"


def test_project_all_is_json_safe(asymmetric):
    """The bundle is written to JSON; numpy floats are not serialisable."""
    import json
    json.dumps(project_all(asymmetric))


# -------------------------------------------------------- degenerate
def test_a_certain_nil_nil_projects_coherently():
    g = _grid({(0, 0): 1.0})
    assert one_x_two(g)["draw"] == pytest.approx(1.0)
    assert over_under(g, 0.5)["under"] == pytest.approx(1.0)
    assert both_teams_to_score(g)["no"] == pytest.approx(1.0)
    assert clean_sheet(g) == {"home": pytest.approx(1.0),
                              "away": pytest.approx(1.0)}


def test_truncation_is_reported_not_hidden():
    """An 11x11 grid cannot represent 11+ goals. Over-lines at or beyond the
    truncation edge are unanswerable, and saying 0% there would be a lie."""
    g = _grid({(0, 0): 1.0}, size=6)              # max total = 10
    with pytest.raises(MarketError, match="truncat"):
        over_under(g, 10.5)
