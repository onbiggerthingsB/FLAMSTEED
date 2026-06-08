import numpy as np, pandas as pd
import pytest
from wcmodel.data.elo import compute_elo_history, elo_1x2_baseline, _mov_index

def _matches():
    return pd.DataFrame([
        {"match_id":"m1","date":"2024-01-01","home_team":"A","away_team":"B",
         "home_score":2,"away_score":0,"neutral":False,"match_type":"friendly"},
        {"match_id":"m2","date":"2024-02-01","home_team":"B","away_team":"A",
         "home_score":1,"away_score":1,"neutral":True,"match_type":"wc_qualifier"},
    ])

def test_elo_is_deterministic_and_point_in_time():
    h1 = compute_elo_history(_matches()); h2 = compute_elo_history(_matches())
    assert h1.equals(h2)
    first = h1[(h1.match_id=="m1") & (h1.team=="A")].iloc[0]
    assert first["rating_pre"] == 1500.0      # debutant starts at initial_rating

def test_winner_gains_rating():
    h = compute_elo_history(_matches())
    a_after_m1 = h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["rating_post"]
    assert a_after_m1 > 1500.0

def test_baseline_probs_sum_to_one_and_favor_higher_rating():
    p = elo_1x2_baseline(rating_home=1800, rating_away=1500, neutral=False)
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
    assert p["home"] > p["away"]

def test_baseline_uses_same_ratings_as_feature():
    h = compute_elo_history(_matches())
    row = h[(h.match_id=="m2")].iloc[0]
    p = elo_1x2_baseline(rating_home=row["rating_pre"], rating_away=1500, neutral=row["neutral"])
    assert set(p) == {"home","draw","away"}

def test_debutant_flagged_provisional():
    h = compute_elo_history(_matches())
    assert h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["provisional"] == True

def test_rating_pre_chains_forward_from_prior_post():
    h = compute_elo_history(_matches())
    a_m1_post = h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["rating_post"]
    a_m2_pre  = h[(h.match_id=="m2") & (h.team=="A")].iloc[0]["rating_pre"]
    assert a_m2_pre == a_m1_post   # no same-match leakage

def test_m1_exact_ratings():
    h = compute_elo_history(_matches())
    a = h[(h.match_id=="m1") & (h.team=="A")].iloc[0]["rating_post"]
    b = h[(h.match_id=="m1") & (h.team=="B")].iloc[0]["rating_post"]
    assert a == pytest.approx(1508.6384400047307)   # 2-0 friendly, non-neutral (ha=100), K=16, G=1.5
    assert b == pytest.approx(1491.3615599952693)

def test_elo_is_input_row_order_invariant():
    """Reproducibility fix: ``compute_elo_history`` sorts by ``(date, match_id)``,
    a TOTAL order fixed by content — so a SHUFFLED input frame yields the IDENTICAL
    ratings/flags. Before the fix the sort was stable-on-``date`` only, so same-date
    matches kept the incoming row order; the upstream DuckDB ``store.read`` returns
    rows in a process-unstable order, which made the SAME data produce slightly
    different ratings + ``provisional`` flags run-to-run and flipped the content-
    addressed feature/posterior cache key (forcing a full re-fit every re-run).

    Two SAME-DATE matches that share a team (so Elo is genuinely path-dependent
    within the day) make this bite: the two input orderings would diverge under
    the old stable-date sort, and must now agree exactly."""
    rows = [
        {"match_id": "a1", "date": "2024-03-01", "home_team": "X", "away_team": "Y",
         "home_score": 3, "away_score": 0, "neutral": False, "match_type": "friendly"},
        {"match_id": "a2", "date": "2024-03-01", "home_team": "X", "away_team": "Z",
         "home_score": 0, "away_score": 2, "neutral": False, "match_type": "friendly"},
        {"match_id": "a3", "date": "2024-03-01", "home_team": "Y", "away_team": "Z",
         "home_score": 1, "away_score": 1, "neutral": True, "match_type": "wc_qualifier"},
    ]
    forward = pd.DataFrame(rows)
    reversed_ = pd.DataFrame(list(reversed(rows)))
    h_fwd = compute_elo_history(forward).sort_values(
        ["match_id", "team"]).reset_index(drop=True)
    h_rev = compute_elo_history(reversed_).sort_values(
        ["match_id", "team"]).reset_index(drop=True)
    assert h_fwd.equals(h_rev), (
        "compute_elo_history must be invariant to input row order (sorted by "
        "(date, match_id)) — else the cache key is non-reproducible")


def test_mov_index_scheme():
    assert _mov_index(1) == 1.0
    assert _mov_index(2) == 1.5
    assert _mov_index(5) == 2.0   # (11+5)/8

def test_baseline_home_advantage_and_neutral_symmetry():
    assert elo_1x2_baseline(1500, 1500, neutral=False)["home"] > 0.5
    pn = elo_1x2_baseline(1500, 1500, neutral=True)
    assert pn["home"] == pytest.approx(pn["away"])   # symmetric when neutral + equal ratings

def test_baseline_draw_peaks_at_even_match():
    assert elo_1x2_baseline(1500, 1500, neutral=True)["draw"] == pytest.approx(0.28)
    assert elo_1x2_baseline(1900, 1500, neutral=True)["draw"] < 0.28


# --- RIDER 1: data-driven provisional (count OR recent volatility) ------------
#
# `provisional` is True if the team had played fewer than `provisional_games`
# matches before this one (count branch) OR its recent rating-delta volatility
# (std of the last `volatility_window` PRIOR deltas, computed causally) exceeds
# `provisional_volatility_threshold`. The three tests below isolate each regime;
# tests 2 and 3 push the team WELL PAST provisional_games so ONLY the volatility
# branch can decide the final-match flag (the count branch is already False).


def _focal_last_row(history: pd.DataFrame, team: str, match_id: str) -> pd.Series:
    return history[(history.team == team) & (history.match_id == match_id)].iloc[0]


def test_few_matches_team_is_provisional():
    """Count branch: a team with < provisional_games (=5) matches is provisional
    on its early matches regardless of volatility."""
    h = compute_elo_history(_matches())          # team A plays only 2 matches
    assert _focal_last_row(h, "A", "m1")["provisional"] == True   # 0 prior
    assert _focal_last_row(h, "A", "m2")["provisional"] == True   # 1 prior (< 5)


def test_many_stable_matches_team_is_not_provisional():
    """A team with MANY matches (count branch satisfied) whose recent rating
    deltas are tiny (repeated draws vs an equal-rated opponent -> std ~0, far
    below the empirically-derived 16.5-pt threshold) is NOT provisional on its
    latest match."""
    rows = []
    # 16 draws: F vs an always-equal-rated opponent. Every result is a draw
    # against a side at F's own rating, so each delta is ~0 -> volatility ~0.
    for i in range(16):
        rows.append({
            "match_id": f"s{i}", "date": f"2024-01-{i + 1:02d}",
            "home_team": "F", "away_team": f"Eq{i}",
            "home_score": 1, "away_score": 1,      # draw
            "neutral": True, "match_type": "friendly",
        })
        # Seed each fresh opponent to F's CURRENT rating via a prior mirror draw
        # is unnecessary: opponents start at 1500 and so does F; F's repeated
        # draws keep it pinned near 1500, so deltas stay ~0 throughout.
    h = compute_elo_history(pd.DataFrame(rows))
    last = _focal_last_row(h, "F", "s15")
    assert last["provisional"] == False           # >5 matches AND low volatility


def test_steadily_favoured_strong_team_is_not_provisional():
    """A settled, well-estimated strong side is also NOT provisional. F beats a
    FRESH 1500-rated opponent 2-0 every match (wc_qualifier, K=32): a consistent
    result against the same starting gap, so the rating deltas barely vary and
    the recent-window std (~2 pts) stays far below the 16.5-pt threshold. This is
    the second settled regime (alongside repeated draws) that must NOT be flagged
    — the threshold separates erratic swings, not steady dominance."""
    rows = []
    for i in range(16):
        rows.append({
            "match_id": f"w{i}", "date": f"2024-03-{i + 1:02d}",
            "home_team": "F", "away_team": f"Weak{i}",   # fresh weak opponent
            "home_score": 2, "away_score": 0,            # steady 2-0 win
            "neutral": True, "match_type": "wc_qualifier",
        })
    h = compute_elo_history(pd.DataFrame(rows))
    last = _focal_last_row(h, "F", "w15")
    assert last["provisional"] == False           # >5 matches AND low volatility


def test_many_but_recently_volatile_team_is_provisional():
    """A team with MANY matches (count branch satisfied) but swinging recent
    ratings IS provisional. F alternates a 2-0 WIN and a 0-2 LOSS against a FRESH
    1500-rated opponent each match (wc_qualifier, K=32); fresh opponents hold the
    expectancy near even so each result lands ~±16 pts off expectation and the
    recent-window std (~25 pts) sits comfortably above the empirically-derived
    16.5-pt threshold (which is the p95 of the real martj42 windowed-stddev
    distribution; ~25 is in its p99.9–max tail — a *realistic* erratic side, not
    the old all-out-thrashing synthetic). A distinct opponent per match keeps the
    gap from converging and decaying the swing below threshold."""
    rows = []
    for i in range(16):
        opp = f"Opp{i}"                              # FRESH opponent each match
        if i % 2 == 0:                              # F wins by two
            hs, as_ = 2, 0
        else:                                       # F loses by two
            hs, as_ = 0, 2
        rows.append({
            "match_id": f"v{i}", "date": f"2024-02-{i + 1:02d}",
            "home_team": "F", "away_team": opp,
            "home_score": hs, "away_score": as_,
            "neutral": True, "match_type": "wc_qualifier",
        })
    h = compute_elo_history(pd.DataFrame(rows))
    last = _focal_last_row(h, "F", "v15")
    # Past provisional_games (16 > 5) so the COUNT branch is False; only the
    # volatility branch can flip this True -> proves the volatility logic fires.
    assert last["provisional"] == True
