import pytest

from wcmodel.dashboard.edges import edges_by_event


class _FakeRanked:
    is_synthetic = True
    opportunities = [{
        "event_key": ["Spain", "Morocco", "2026-06-11"], "staked": "home",
        "edge": 0.04, "liquidity": 50.0, "stake_signal": 1.1,
        "entry_odds": 2.5, "close_odds": 2.1,
        "model": {"home": 0.62, "draw": 0.24, "away": 0.14},
        "is_synthetic": True,
    }]
    non_bets = {"no_odds": 1}


def test_edges_carry_real_scan_fields_and_synthetic_taint():
    out = edges_by_event(_FakeRanked())
    key = ("Spain", "Morocco", "2026-06-11")
    node = out[key]
    assert node["staked"] == "home"
    assert node["edge"] == 0.04                       # scalar
    assert node["stake_signal"] == 1.1               # SIGNAL, not "stake"
    assert node["entry_odds"] == 2.5                  # scalar (staked side, decision-time ENTRY <= cutoff)
    assert node["is_synthetic"] is True              # taint rode in
    assert "stake" not in node                       # the wrong plan key is gone


def test_edge_node_omits_post_cutoff_close_and_bare_model(
):
    """HIGH-4 / MED-5 (C5 FOCAL Codex): the as-of-cutoff dashboard edge node must NOT carry

      * ``close_odds`` (HIGH-4) — the close is the latest <= kickoff line, i.e. FUTURE info at
        a pre-kickoff cutoff; publishing it in the as-of-cutoff snapshot LEAKS a post-cutoff
        price. Realized CLV (entry vs close) is the LIVE paper tracker's job (Phase 5), computed
        POST-match, not the as-of-cutoff dashboard.
      * ``model`` (MED-5) — a bare 1X2 probability triple escapes any gate (a naked-probability
        surface). The gated 1X2 lives in the fixture forecast's ``one_x_two`` (gate_fixture_
        forecast, all three outcomes), so the edge node must not duplicate an ungated copy.

    The dashboard edge node = the decision-time fields ``{staked, edge, stake_signal,
    entry_odds, is_synthetic}`` PLUS the DERIVED de-vigged ENTRY ``market_1x2`` WHEN a valid
    one exists (``_FakeRanked`` carries none, so its node is exactly the base set). The bare
    ``model`` triple and the post-cutoff ``close_odds`` are still NEVER carried. RED before the
    fix (the node carried close_odds + model); GREEN after."""
    out = edges_by_event(_FakeRanked())
    node = out[("Spain", "Morocco", "2026-06-11")]
    assert "close_odds" not in node, (
        "post-cutoff close_odds leaked into the as-of-cutoff dashboard edge node (HIGH-4)")
    assert "model" not in node, (
        "a bare, ungated 1X2 model triple escaped into the edge node (MED-5)")
    # _FakeRanked carries NO market_1x2 -> the node is EXACTLY the decision-time base set
    # (no realized-CLV, no naked model, no fabricated market line).
    assert set(node) == {"staked", "edge", "stake_signal", "entry_odds", "is_synthetic"}


def test_missing_edge_is_a_coverage_gap_not_a_number():
    out = edges_by_event(_FakeRanked())
    assert ("Germany", "Japan", "2026-06-12") not in out   # no fabricated edge


def test_taint_propagates_if_either_ranked_or_opp_is_synthetic():
    class _Mixed:
        is_synthetic = False
        opportunities = [{
            "event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
            "liquidity": 10.0, "stake_signal": 0.5, "entry_odds": 2.0, "close_odds": 1.9,
            "model": {"home": 0.5, "draw": 0.3, "away": 0.2}, "is_synthetic": True,
        }]
        non_bets = {}
    out = edges_by_event(_Mixed())
    assert out[("A", "B", "2026-06-11")]["is_synthetic"] is True   # opp-level taint wins


def test_edge_node_does_not_read_model_or_close_so_their_absence_is_harmless():
    """MED-5 / HIGH-4 corollary: since the edge node no longer carries ``model`` or
    ``close_odds``, an opportunity LACKING them must NOT raise — the node is built purely from
    the decision-time fields. (Pre-fix, a missing ``model`` was a strict-read KeyError; that
    strict read is gone now that the bare model is dropped.)"""
    class _NoModelNoClose:
        is_synthetic = True
        opportunities = [{
            "event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
            "stake_signal": 0.5, "entry_odds": 2.0,
            "is_synthetic": True,   # NO "model", NO "close_odds" -> still builds the node
        }]
        non_bets = {}
    out = edges_by_event(_NoModelNoClose())          # must NOT raise
    assert set(out[("A", "B", "2026-06-11")]) == {
        "staked", "edge", "stake_signal", "entry_odds", "is_synthetic"}


def test_missing_opp_taint_defaults_NON_REAL_never_silently_real():
    class _NoTaint:
        is_synthetic = False        # ranked-level says real...
        opportunities = [{
            "event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
            "liquidity": 10.0, "stake_signal": 0.5, "entry_odds": 2.0, "close_odds": 1.9,
            "model": {"home": 0.5, "draw": 0.3, "away": 0.2},
            # NOTE: no "is_synthetic" on the opp -> must FAIL SAFE to True, not silently real
        }]
        non_bets = {}
    out = edges_by_event(_NoTaint())
    assert out[("A", "B", "2026-06-11")]["is_synthetic"] is True   # fail-safe NON-REAL


# ── GHOST LINE: the de-vigged ENTRY market 1X2 (derived comparison) ────────────────


class _RankedWithMarket:
    """A scan whose opportunity carries the de-vigged ENTRY market 1X2 (``market_entry`` on
    the LiveDecision -> ``market_1x2`` on the scan opportunity). Mirrors the real shape: the
    market line is the de-vig of the DECISION-TIME ENTRY odds (<= cutoff, leakage-safe)."""
    is_synthetic = True
    opportunities = [{
        "event_key": ["Spain", "Morocco", "2026-06-11"], "staked": "home",
        "edge": 0.04, "liquidity": 50.0, "stake_signal": 1.1,
        "entry_odds": 2.5, "close_odds": 2.1,
        "model": {"home": 0.62, "draw": 0.24, "away": 0.14},
        "market_1x2": {"home": 0.58, "draw": 0.25, "away": 0.17},   # de-vigged ENTRY, sums to 1
        "is_synthetic": True,
    }]
    non_bets = {}


def test_edge_node_emits_devigged_market_1x2_from_entry_odds():
    """The edge node carries the de-vigged ENTRY market 1X2 (a DERIVED comparison, like the
    edge — NOT a forecast estimate, so NO uncertainty companion). It must be a finite,
    all-three, sum~1 distribution. RED before the feature (no market_1x2 emitted); GREEN
    after."""
    out = edges_by_event(_RankedWithMarket())
    node = out[("Spain", "Morocco", "2026-06-11")]
    m = node["market_1x2"]
    assert set(m) == {"home", "draw", "away"}                      # all three outcomes
    assert all(isinstance(m[o], float) and 0.0 <= m[o] <= 1.0 for o in m)
    assert abs(sum(m.values()) - 1.0) < 1e-6                       # sums to ~1 (de-vigged)


def test_edge_node_omits_market_1x2_when_no_market_or_degenerate():
    """The market line is emitted ONLY where a real, valid de-vigged ENTRY 1X2 exists. An
    opportunity lacking ``market_1x2``, or carrying a degenerate one (non-finite / out of
    [0,1] / not summing to 1), emits NO market line — never a fabricated/unsafe number."""
    class _Cases:
        is_synthetic = True
        opportunities = [
            # (1) no market_1x2 at all -> omit
            {"event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
             "stake_signal": 0.5, "entry_odds": 2.0, "is_synthetic": True},
            # (2) a NaN outcome -> degenerate -> omit
            {"event_key": ["C", "D", "2026-06-11"], "staked": "home", "edge": 0.02,
             "stake_signal": 0.5, "entry_odds": 2.0, "is_synthetic": True,
             "market_1x2": {"home": float("nan"), "draw": 0.3, "away": 0.4}},
            # (3) does not sum to 1 -> degenerate -> omit
            {"event_key": ["E", "F", "2026-06-11"], "staked": "home", "edge": 0.02,
             "stake_signal": 0.5, "entry_odds": 2.0, "is_synthetic": True,
             "market_1x2": {"home": 0.2, "draw": 0.2, "away": 0.2}},
            # (4) missing an outcome -> degenerate -> omit
            {"event_key": ["G", "H", "2026-06-11"], "staked": "home", "edge": 0.02,
             "stake_signal": 0.5, "entry_odds": 2.0, "is_synthetic": True,
             "market_1x2": {"home": 0.5, "away": 0.5}},
        ]
        non_bets = {}
    out = edges_by_event(_Cases())
    for key in [("A", "B", "2026-06-11"), ("C", "D", "2026-06-11"),
                ("E", "F", "2026-06-11"), ("G", "H", "2026-06-11")]:
        assert "market_1x2" not in out[key], f"a degenerate/absent market line was emitted for {key}"


def test_market_1x2_is_a_copy_not_an_alias_of_the_opp_dict():
    """The emitted market line is a fresh ``{home, draw, away}`` of floats — not an alias of
    the opportunity's dict (so mutating the source never mutates the bundle)."""
    src = _RankedWithMarket()
    out = edges_by_event(src)
    node = out[("Spain", "Morocco", "2026-06-11")]
    assert node["market_1x2"] is not src.opportunities[0]["market_1x2"]
    assert all(isinstance(v, float) for v in node["market_1x2"].values())
