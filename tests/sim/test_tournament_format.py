"""Phase-2A Task 4 — format threading through the sim loop.

Four independently-checkable contracts:

  1. **Slot grammar** — the feeder regexes in ``sim/tournament.py`` are no longer
     capped at the WC's 12 group letters / 5-letter third sets: ``1M`` is a valid
     group slot and ``3rd-ABC`` a valid best-third slot (AFC Asian Cup 2027
     publishes 3-letter eligible sets).
  2. **Hosts at the source** — ``host_home_factor`` takes an explicit ``hosts``
     map; ``hosts=None`` reproduces the frozen WC-2026 module literal EXACTLY, so
     every pre-change call site is byte-identical.
  3. **KO host policy** — ``_ko_host_side`` implements the exactly-one-host rule
     (both hosts / neither host => neutral), and the policy only fires when the
     format opts in (``ko_host_advantage``), so the WC path is untouched.
  4. **fmt threading** — ``tiebreak_order`` / ``best_thirds`` / ``assignment_table``
     actually reach ``rank_group`` / ``rank_thirds`` / ``assign_thirds_to_slots``,
     and an ABSENT fmt reproduces the frozen defaults bit-for-bit.
"""
from __future__ import annotations

import pytest

from wcmodel.data.tournament import HOST_COUNTRY_BY_TEAM, host_home_factor
from wcmodel.sim.bracket import build_bracket
from wcmodel.sim.tournament import (_ko_host_side, _resolve_feeder,
                                    simulate_tournament)

from tests.sim.conftest import tiny_bracket
from tests.sim.test_sim_cache import _toy_posterior

_CFG = {"model": {"covariates": {"host_k": 0.6}}}
_AC_HOSTS = {"Saudi Arabia": "SA"}


# ---------------------------------------------------------------------------
# 1. Slot grammar (regexes generalized beyond the WC's A..L / 5-letter sets)
# ---------------------------------------------------------------------------
def test_group_slot_ref_beyond_letter_l_resolves():
    """``1M`` — a 13th group letter. The WC regex ``[A-L]`` silently REFUSED it
    (falling through to the unrecognised-token raise), which would break any
    edition with more than 12 groups."""
    team = _resolve_feeder("1M", group_rankings={"M": ["w", "x", "y", "z"]},
                           third_by_match={}, winners={}, losers={}, match_no=1)
    assert team == "w"


def test_short_third_slot_ref_resolves():
    """``3rd-ABC`` — the AFC's 3-letter eligible set. The third-placer of the
    ASSIGNED group (index 2 of that group's ranking) fills the slot."""
    team = _resolve_feeder("3rd-ABC", group_rankings={"B": ["w", "x", "y", "z"]},
                           third_by_match={7: "B"}, winners={}, losers={}, match_no=7)
    assert team == "y"


# ---------------------------------------------------------------------------
# 2. Hosts fixed at the source (host_home_factor itself, not just the map)
# ---------------------------------------------------------------------------
def test_host_home_factor_honours_explicit_hosts_map():
    venues = {"Riyadh": "SA"}
    assert host_home_factor("Saudi Arabia", "Japan", "Riyadh", venues, _CFG,
                            hosts=_AC_HOSTS) == 0.6
    # The WC literal must NOT leak in when an explicit map is supplied.
    assert host_home_factor("Mexico", "Japan", "Riyadh", venues, _CFG,
                            hosts=_AC_HOSTS) is None
    # ... and the AC host gets nothing at an out-of-country venue.
    assert host_home_factor("Saudi Arabia", "Japan", "Doha", {"Doha": "QA"}, _CFG,
                            hosts=_AC_HOSTS) is None


def test_host_home_factor_default_is_the_frozen_wc_literal():
    venues = {"Guadalajara": "MX", "Riyadh": "SA"}
    assert host_home_factor("Mexico", "Japan", "Guadalajara", venues, _CFG) == 0.6
    assert host_home_factor("Saudi Arabia", "Japan", "Riyadh", venues, _CFG) is None
    assert host_home_factor("Mexico", "Japan", "Guadalajara", venues, _CFG,
                            hosts=HOST_COUNTRY_BY_TEAM) == 0.6


# ---------------------------------------------------------------------------
# 3. KO host policy — the exactly-one-host rule
# ---------------------------------------------------------------------------
def test_ko_host_side_exactly_one_host():
    assert _ko_host_side("Saudi Arabia", "Japan", _AC_HOSTS) == "home"
    assert _ko_host_side("Japan", "Saudi Arabia", _AC_HOSTS) == "away"


def test_ko_host_side_both_or_neither_is_neutral():
    assert _ko_host_side("Japan", "Iran", _AC_HOSTS) is None
    assert _ko_host_side("Qatar", "Saudi Arabia",
                         {"Qatar": "QA", "Saudi Arabia": "SA"}) is None
    assert _ko_host_side("Japan", "Iran", {}) is None


# ---------------------------------------------------------------------------
# 4. fmt threading end-to-end through simulate_tournament
# ---------------------------------------------------------------------------
def _sim_kwargs(**over):
    kw = dict(bracket=tiny_bracket(), n_sims=250, seed=7, max_goals=8,
              et_scale=0.3333, pen_home_prob=0.5)
    kw.update(over)
    return kw


def test_absent_fmt_equals_explicit_wc_defaults():
    """fmt=None and an fmt carrying the WC values produce the IDENTICAL frame —
    the defaults baked into ``simulate_one`` are exactly the frozen ones."""
    post = _toy_posterior()
    base = simulate_tournament(post, **_sim_kwargs())
    same = simulate_tournament(post, **_sim_kwargs(), fmt={
        "tiebreak_order": "fifa_2026", "best_thirds": 8,
        "assignment_table": "third_place_assignment.json",
        "hosts": dict(HOST_COUNTRY_BY_TEAM), "ko_host_advantage": False})
    assert same.progression.equals(base.progression)
    assert same.se.equals(base.se)


def test_fmt_tiebreak_order_reaches_rank_group():
    """An unknown order must blow up FROM ``rank_group`` — proof the fmt value is
    threaded rather than dropped (a dropped value would silently sim as FIFA)."""
    with pytest.raises(ValueError, match="unknown tiebreak order"):
        simulate_tournament(_toy_posterior(), **_sim_kwargs(n_sims=1),
                            fmt={"tiebreak_order": "uefa"})


def _thirds_bracket():
    """Two groups A/B; match 1 carries a ``3rd-AB`` slot so the thirds block runs."""
    a = ["Brazil", "Argentina", "Croatia", "France"]
    b = ["Spain", "Germany", "Italy", "Portugal"]

    def _rr(t):
        return [(t[0], t[1]), (t[2], t[3]), (t[0], t[2]),
                (t[1], t[3]), (t[0], t[3]), (t[1], t[2])]

    tournament = {
        "groups": [{"name": "A", "teams": a}, {"name": "B", "teams": b}],
        "fixtures": [
            *[{"home": h, "away": w, "round": "Matchday 1", "group": "A"}
              for h, w in _rr(a)],
            *[{"home": h, "away": w, "round": "Matchday 1", "group": "B"}
              for h, w in _rr(b)],
            {"match": 1, "home": "1A", "away": "3rd-AB", "round": "Semi-final"},
            {"match": 2, "home": "1B", "away": "2A", "round": "Semi-final"},
            {"match": 3, "home": "W1", "away": "W2", "round": "Final"},
        ],
    }
    return build_bracket(tournament)


def test_fmt_thirds_kwargs_reach_rank_thirds_and_assignment(monkeypatch):
    """``best_thirds`` -> ``rank_thirds(best_n=...)`` and ``assignment_table`` ->
    ``assign_thirds_to_slots(table_file=...)``. Both are captured at the sim's
    call boundary, so the assertion is about THREADING, not about the AC table
    (which the Task-5 acceptance run exercises for real)."""
    import wcmodel.sim.tournament as st

    seen = {}

    def fake_rank_thirds(thirds, *, rng, best_n=8):
        seen["best_n"] = best_n
        return sorted(thirds)[:1]

    def fake_assign(qualifying, *, table_file="third_place_assignment.json"):
        seen["table_file"] = table_file
        return {1: sorted(qualifying)[0]}

    monkeypatch.setattr(st, "rank_thirds", fake_rank_thirds)
    monkeypatch.setattr(st, "assign_thirds_to_slots", fake_assign)

    post = _toy_posterior(teams=["Brazil", "Argentina", "Croatia", "France",
                                 "Spain", "Germany", "Italy", "Portugal"])
    simulate_tournament(post, **_sim_kwargs(bracket=_thirds_bracket(), n_sims=3),
                        fmt={"best_thirds": 4,
                             "assignment_table": "third_place_assignment_ac2027.json"})
    assert seen == {"best_n": 4,
                    "table_file": "third_place_assignment_ac2027.json"}


def test_ko_host_advantage_is_opt_in_and_moves_the_champion_market():
    """Policy OFF (the WC default) => byte-identical to no fmt at all. Policy ON
    => the host's Final is no longer neutral, so its champion share rises."""
    post = _toy_posterior()
    base = simulate_tournament(post, **_sim_kwargs())
    off = simulate_tournament(post, **_sim_kwargs(),
                              fmt={"hosts": {"Brazil": "BR"},
                                   "ko_host_advantage": False},
                              ko_host_factor=5.0)
    on = simulate_tournament(post, **_sim_kwargs(),
                             fmt={"hosts": {"Brazil": "BR"},
                                  "ko_host_advantage": True},
                             ko_host_factor=5.0)
    assert off.progression.equals(base.progression), "policy off must not touch output"
    assert not on.progression.equals(base.progression), "policy on must change output"
    assert (on.progression.loc["Brazil", "champion"]
            > base.progression.loc["Brazil", "champion"])
    # The host advantage is a KO-resolution effect only: group placings (which are
    # decided before any KO match) are untouched.
    assert on.progression["first"].equals(base.progression["first"])
