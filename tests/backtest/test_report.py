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
    # a genuinely-informative model beats most shuffles (high percentile of the null).
    assert res["percentile"] > 0.90
    # seeded -> reproducible.
    res2 = permutation_null(model_probs, outcomes, shuffles=200, seed=20260611)
    assert res == res2
