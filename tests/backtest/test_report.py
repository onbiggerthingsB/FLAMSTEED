import numpy as np

from wcmodel.backtest.report import (
    lockbox_split, stratify, baseline_beat_verdict, permutation_null,
    stratum_is_coverage_gap, render_stratum, MIN_STRATUM_N,
)


def test_lockbox_split_is_final_18pct_by_date():
    dates = [f"2020-01-{d:02d}" for d in range(1, 21)]   # 20 dated bets
    bets = [{"cutoff": d, "pnl": 0.0, "stake": 1.0} for d in dates]
    tuned, lock = lockbox_split(bets, lockbox_fraction=0.18)
    # final 18% by date => last ~4 of 20 dates are frozen.
    assert len(lock) == 4 and len(tuned) == 16
    # the lockbox holds the LATEST dates (frozen tail).
    assert min(b["cutoff"] for b in lock) > max(b["cutoff"] for b in tuned)


def test_lockbox_split_never_bleeds_a_tied_boundary_date_into_tuning():
    """Codex P1(c): when multiple bets SHARE the boundary cutoff date, the split is
    BY DATE — every bet on the boundary date goes together into the lockbox, never
    straddling the boundary. A late date can never leak into the tuned set even
    though a raw count slice (round(N*frac)) would split that date."""
    # 16 distinct early dates (one bet each) + a final matchday with 5 tied bets.
    early = [{"cutoff": f"2020-01-{d:02d}", "pnl": 0.0, "stake": 1.0}
             for d in range(1, 17)]
    boundary = [{"cutoff": "2020-01-17", "pnl": 0.0, "stake": 1.0} for _ in range(5)]
    bets = early + boundary                            # N=21, round(21*0.18)=4
    tuned, lock = lockbox_split(bets, lockbox_fraction=0.18)
    # A count slice would keep 1 of the 5 tied "2020-01-17" bets in `tuned`; the
    # by-date split must pull ALL FIVE into the lockbox.
    assert all(b["cutoff"] != "2020-01-17" for b in tuned)   # no boundary date leaks
    assert sum(1 for b in lock if b["cutoff"] == "2020-01-17") == 5
    # strict separation by date still holds (frozen tail is the latest dates).
    assert min(b["cutoff"] for b in lock) > max(b["cutoff"] for b in tuned)


def test_stratify_groups_by_tier_and_flags_thin_strata():
    bets = (
        [{"match_type": "wc_finals", "confederation_home": "UEFA", "pnl": 1.0,
          "stake": 1.0, "entry_odds": 2.0, "close_odds": 1.9, "rps_model": 0.1,
          "rps_market": 0.2, "rps_elo": 0.3} for _ in range(40)]
        + [{"match_type": "friendly", "confederation_home": "CAF", "pnl": -1.0,
            "stake": 1.0, "entry_odds": 2.0, "close_odds": 2.1, "rps_model": 0.4,
            "rps_market": 0.2, "rps_elo": 0.3} for _ in range(2)]
    )
    strata = stratify(bets, by="match_type")
    assert "wc_finals" in strata and "friendly" in strata
    # the thin friendly stratum is a COVERAGE GAP (n below the floor), never averaged.
    assert stratum_is_coverage_gap(strata["friendly"]) is True
    assert stratum_is_coverage_gap(strata["wc_finals"]) is False
    # a healthy stratum carries CLV + ROI + n.
    assert strata["wc_finals"]["n_bets"] == 40
    assert "clv_beat_close_rate" in strata["wc_finals"]

    # RENDERING (rider #5): the thin tier renders as an EXPLICIT coverage gap tied
    # to its denominator — "insufficient coverage (n=<k>)", NEVER a number.
    thin = render_stratum(strata["friendly"])
    assert thin["coverage_gap"] is True
    assert thin["render"] == "insufficient coverage (n=2)"
    assert "clv_beat_close_rate" not in thin and "roi_roi" not in thin   # no number leaks
    # the healthy tier renders its real metrics.
    healthy = render_stratum(strata["wc_finals"])
    assert healthy["coverage_gap"] is False
    assert "clv_beat_close_rate" in healthy and healthy["n_bets"] == 40


def test_baseline_beat_verdict_states_beat_both_or_not():
    # model RPS below BOTH baselines AND positive ROI => beats both.
    summ = {"mean_rps_model": 0.18, "mean_rps_market": 0.20, "mean_rps_elo": 0.22,
            "roi_roi": 0.03}
    v = baseline_beat_verdict(summ)
    assert v["beats_market_rps"] and v["beats_elo_rps"]
    assert v["beats_both"] is True
    # model worse than market RPS => does NOT beat both (report says so plainly).
    summ2 = dict(summ, mean_rps_model=0.21)
    assert baseline_beat_verdict(summ2)["beats_both"] is False


def test_baseline_beat_verdict_fails_on_missing_or_nonfinite_baseline():
    """Codex P2(d): a missing or non-finite baseline RPS can NEVER silently pass.
    The verdict requires beating BOTH PRESENT, finite baselines — an absent baseline
    is treated as not-beaten, not defaulted to inf (which would auto-pass)."""
    # market baseline ABSENT: must NOT count as beaten, so beats_both is False even
    # with a great model RPS and positive ROI.
    no_market = {"mean_rps_model": 0.05, "mean_rps_elo": 0.22, "roi_roi": 0.03}
    v = baseline_beat_verdict(no_market)
    assert v["beats_market_rps"] is False     # absent baseline is not a beat
    assert v["beats_both"] is False
    # elo baseline present but NaN: also not a beat.
    nan_elo = {"mean_rps_model": 0.05, "mean_rps_market": 0.20,
               "mean_rps_elo": float("nan"), "roi_roi": 0.03}
    assert baseline_beat_verdict(nan_elo)["beats_elo_rps"] is False
    assert baseline_beat_verdict(nan_elo)["beats_both"] is False
    # a non-finite MODEL RPS likewise fails both (nothing to compare).
    nan_model = {"mean_rps_model": float("nan"), "mean_rps_market": 0.20,
                 "mean_rps_elo": 0.22, "roi_roi": 0.03}
    vm = baseline_beat_verdict(nan_model)
    assert vm["beats_market_rps"] is False and vm["beats_elo_rps"] is False
    assert vm["beats_both"] is False


def test_permutation_null_places_model_score_and_is_seeded():
    rng = np.random.default_rng(0)
    # model probs that genuinely track outcomes -> low RPS vs shuffled labels.
    outcomes = ["home", "away", "draw"] * 20
    model_probs = [
        {"home": 0.7, "draw": 0.2, "away": 0.1} if o == "home" else
        ({"home": 0.1, "draw": 0.2, "away": 0.7} if o == "away" else
         {"home": 0.25, "draw": 0.5, "away": 0.25})
        for o in outcomes
    ]
    res = permutation_null(model_probs, outcomes, shuffles=200, seed=20260611)
    assert res["n_shuffles"] == 200
    assert 0.0 <= res["percentile"] <= 1.0
    # a genuinely-informative model clears the D4 ~99th-percentile bar.
    assert res["percentile"] >= 0.99
    # seeded -> reproducible.
    res2 = permutation_null(model_probs, outcomes, shuffles=200, seed=20260611)
    assert res == res2


def test_permutation_null_refuses_under_sampling():
    # D4: an under-sampled null (below the pre-registered minimum 200) reports a
    # misleadingly-precise percentile and must RAISE, not be silently reported.
    import pytest
    outcomes = ["home", "away", "draw"] * 20
    probs = [{"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3} for _ in outcomes]
    for bad in (1, 50, 199):
        with pytest.raises(ValueError):
            permutation_null(probs, outcomes, shuffles=bad, seed=0)
    permutation_null(probs, outcomes, shuffles=200, seed=0)   # exactly the minimum is allowed


def test_permutation_null_refuses_length_mismatch_and_bad_outcomes():
    # A length mismatch (a silent zip-truncation would score a SUBSET as if it were
    # the full shuffle), an empty input, and an invalid outcome must all RAISE.
    import pytest
    outcomes = ["home", "away", "draw"] * 20
    probs = [{"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3} for _ in outcomes]
    with pytest.raises(ValueError):
        permutation_null(probs[:10], outcomes, shuffles=200, seed=0)        # length mismatch
    with pytest.raises(ValueError):
        permutation_null([], [], shuffles=200, seed=0)                      # empty
    with pytest.raises(ValueError):
        permutation_null(probs, ["home"] * 59 + ["nope"], shuffles=200, seed=0)  # invalid outcome
