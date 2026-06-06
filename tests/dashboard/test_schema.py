import math
import pytest
from wcmodel.dashboard.schema import (
    validate_progression_coherence, assert_uncertainty_companion, coverage_gap, no_impute,
)


def test_coherence_accepts_monotone_ladder():
    validate_progression_coherence({
        "champion": 0.10, "reach_final": 0.18, "reach_sf": 0.30,
        "reach_qf": 0.45, "advance_from_group": 0.70,
    })  # no raise


def test_coherence_rejects_a_broken_ladder():
    with pytest.raises(ValueError, match="coherence"):
        validate_progression_coherence({
            "champion": 0.20, "reach_final": 0.18,
            "reach_sf": 0.30, "reach_qf": 0.45, "advance_from_group": 0.70,
        })


def test_coherence_includes_reach_r16_in_the_ladder():
    """reach_r16 sits between advance_from_group and reach_qf on the cumulative ladder
    (champion <= reach_final <= reach_sf <= reach_qf <= reach_r16 <= advance_from_group),
    and team_progression emits it — so the coherence gate must check it. A table where
    reach_r16 EXCEEDS advance_from_group (a deeper stage more likely than a shallower one)
    while every other rung is coherent must RAISE. RED before reach_r16 is in _LADDER
    (the rung is silently skipped, so the violation slips through GREEN); GREEN after."""
    with pytest.raises(ValueError, match="coherence"):
        validate_progression_coherence({
            "champion": 0.10, "reach_final": 0.18, "reach_sf": 0.30, "reach_qf": 0.45,
            "reach_r16": 0.80,            # > advance_from_group (0.70): incoherent
            "advance_from_group": 0.70,
        })


def test_coherence_accepts_a_coherent_ladder_with_reach_r16():
    """The full ladder including reach_r16, all monotone -> no raise."""
    validate_progression_coherence({
        "champion": 0.10, "reach_final": 0.18, "reach_sf": 0.30, "reach_qf": 0.45,
        "reach_r16": 0.60, "advance_from_group": 0.70,
    })  # no raise


def test_uncertainty_companion_required_on_every_probability():
    assert_uncertainty_companion({"value": 0.14, "se": 0.02})
    assert_uncertainty_companion({"value": 0.58, "ci": [0.52, 0.63]})
    with pytest.raises(ValueError, match="naked"):
        assert_uncertainty_companion({"value": 0.14})


def test_coverage_gap_is_explicit_not_a_number():
    g = coverage_gap("no outright odds")
    assert g == {"coverage_gap": True, "reason": "no outright odds", "value": None}


def test_no_impute_passes_nan_through_as_null_never_zero():
    assert no_impute(float("nan")) is None
    assert no_impute(1.7) == 1.7


def test_se_zero_is_a_valid_companion_certain_market():
    # an eliminated team: champion prob 0 -> binomial SE exactly 0 -> legitimate, NOT naked
    assert_uncertainty_companion({"value": 0.0, "se": 0.0})   # no raise


def test_degenerate_companions_are_rejected_as_naked():
    for bad in ({"value": 0.1, "se": float("nan")},
                {"value": 0.1, "se": float("inf")},
                {"value": 0.1, "ci": []},
                {"value": 0.1, "ci": [0.5]},
                {"value": 0.1, "ci": [0.5, float("nan")]}):
        with pytest.raises(ValueError, match="naked"):
            assert_uncertainty_companion(bad)


def test_valid_companions_still_pass():
    assert_uncertainty_companion({"value": 0.14, "se": 0.02})        # finite se
    assert_uncertainty_companion({"value": 0.58, "ci": [0.52, 0.63]}) # 2 finite bounds


from wcmodel.dashboard.schema import gate_fixture_forecast, gate_track, gate_schedule


def _good_group_row():
    return {
        "home": "Brazil", "away": "Mexico", "date": "2026-06-12", "stage": "group",
        "forecast_summary": {
            "most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12},
            "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1},
        },
        "edge": {"coverage_gap": True, "reason": "no live edge"},
    }


def _good_ko_row():
    return {
        "match": 73, "stage": "R32", "status": "upcoming",
        "home_ref": "1A", "away_ref": "2A",
        "home_occupants": [{"team": "Brazil", "prob": 0.6, "se": 0.02}],
        "away_occupants": [{"team": "Mexico", "prob": 0.4, "se": 0.02}],
    }


def test_gate_schedule_accepts_a_valid_payload():
    gate_schedule({"group": [_good_group_row()], "knockout": [_good_ko_row()]})  # no raise


def test_gate_schedule_rejects_nan_forecast_summary_prob():
    """FIX D: a GROUP row's forecast_summary headline prob is value-checked (same as FIX C)."""
    row = _good_group_row()
    row["forecast_summary"]["most_likely"]["prob"] = float("nan")
    with pytest.raises(ValueError, match="(?i)most_likely|prob|finite"):
        gate_schedule({"group": [row], "knockout": []})


def test_gate_schedule_rejects_incoherent_forecast_summary_1x2():
    row = _good_group_row()
    row["forecast_summary"]["one_x_two"] = {"home": 0.5, "draw": 0.5, "away": 0.5}  # sums 1.5
    with pytest.raises(ValueError, match="(?i)1x2|sum|distribution"):
        gate_schedule({"group": [row], "knockout": []})


def test_gate_schedule_exempts_coverage_gap_forecast_summary():
    row = _good_group_row()
    row["forecast_summary"] = {"coverage_gap": True, "reason": "no forecast for this fixture"}
    gate_schedule({"group": [row], "knockout": []})  # a gap is an honest absence, not a naked number


def test_gate_schedule_rejects_bad_edge_entry_odds():
    """FIX D: a real edge node's entry_odds must be a finite decimal-odds number > 1.0."""
    row = _good_group_row()
    row["edge"] = {"edge": 0.04, "stake_signal": 0.5, "entry_odds": 0.5}  # < 1.0 is impossible
    with pytest.raises(ValueError, match="(?i)entry_odds|odds|edge"):
        gate_schedule({"group": [row], "knockout": []})


def test_gate_schedule_rejects_nonfinite_edge_fields():
    row = _good_group_row()
    row["edge"] = {"edge": float("nan"), "stake_signal": 0.5, "entry_odds": 2.0}
    with pytest.raises(ValueError, match="(?i)edge|finite"):
        gate_schedule({"group": [row], "knockout": []})


def test_gate_schedule_rejects_naked_occupant_without_se():
    """FIX D: a KO occupant carrying a prob but NO se is a naked number — must raise (the
    occupant-list is supposed to be gapped rather than emit a naked prob, but if a naked
    prob reaches the gate it STOPS the build)."""
    row = _good_ko_row()
    row["home_occupants"] = [{"team": "Brazil", "prob": 0.6}]  # no se
    with pytest.raises(ValueError, match="(?i)occupant|se|naked"):
        gate_schedule({"group": [], "knockout": [row]})


def test_gate_schedule_rejects_out_of_range_occupant_prob():
    row = _good_ko_row()
    row["away_occupants"] = [{"team": "Mexico", "prob": 1.4, "se": 0.02}]
    with pytest.raises(ValueError, match="(?i)occupant|prob|range|finite"):
        gate_schedule({"group": [], "knockout": [row]})


def test_gate_schedule_exempts_coverage_gap_occupants():
    row = _good_ko_row()
    row["home_occupants"] = {"coverage_gap": True, "reason": "feeder resolves later"}
    gate_schedule({"group": [], "knockout": [row]})  # a gap occupant-list is an honest absence


def test_coverage_gap_node_is_exempt_from_naked_check():
    assert_uncertainty_companion(coverage_gap("no odds"))      # no raise (value is None)
    assert_uncertainty_companion({"value": None})              # explicit null is not naked


def test_gate_fixture_forecast_requires_distribution_and_paired_score():
    good = {"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12},
            "shortlist": [{"home_goals": 1, "away_goals": 0, "prob": 0.12}],
            "grid": [[0.5, 0.2], [0.2, 0.1]],
            "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}}
    gate_fixture_forecast(good)                                # grid sums ~1, all three 1X2, paired score
    with pytest.raises(ValueError, match="(?i)grid|1x2|naked"):
        gate_fixture_forecast({"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12}})


def test_gate_fixture_forecast_rejects_a_lone_1x2_outcome():
    f = {"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12},
         "grid": [[0.5, 0.2], [0.2, 0.1]], "one_x_two": {"home": 0.7}}   # only one outcome
    with pytest.raises(ValueError, match="(?i)1x2|three"):
        gate_fixture_forecast(f)


def test_gate_track_rejects_a_nan_metric():
    gate_track({"beat_close_rate": 0.56, "avg_clv": 0.018, "rps": {"model": 0.1}})  # ok
    with pytest.raises(ValueError, match="(?i)nan|finite"):
        gate_track({"beat_close_rate": float("nan")})


def test_coverage_gap_with_a_real_value_is_a_contradiction_and_raises():
    # a coverage_gap MUST have value=None; one carrying a real value must NOT be exempted
    with pytest.raises(ValueError, match="naked"):
        assert_uncertainty_companion({"coverage_gap": True, "value": 0.1})


def test_gate_fixture_forecast_rejects_bad_sum_grid_and_missing_prob():
    base = {"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12},
            "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}}
    with pytest.raises(ValueError, match="(?i)sum|grid"):
        gate_fixture_forecast({**base, "grid": [[0.1, 0.1], [0.1, 0.1]]})   # sums to 0.4, not ~1
    with pytest.raises(ValueError, match="(?i)naked|prob"):
        gate_fixture_forecast({"grid": [[0.5, 0.2], [0.2, 0.1]],
                               "most_likely": {"home_goals": 1, "away_goals": 0},  # no prob
                               "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}})


def test_gate_fixture_forecast_rejects_malformed_grid_with_valueerror():
    with pytest.raises(ValueError, match="(?i)grid"):
        gate_fixture_forecast({"grid": [0.5, 0.5],  # rows not iterable
                               "most_likely": {"home_goals": 0, "away_goals": 0, "prob": 1.0},
                               "one_x_two": {"home": 0.4, "draw": 0.3, "away": 0.3}})


def test_gate_track_recursion_inf_none_and_coverage_gap():
    gate_track({"a": {"b": [1.0, None, 0.5]}, "rps": {"model": 0.1, "elo": None}})   # ok: finite/None
    gate_track({"x": coverage_gap("no backtest")})                                    # ok: gap subtree exempt
    with pytest.raises(ValueError, match="(?i)finite|nan"):
        gate_track({"a": {"b": [1.0, float("inf")]}})                                 # nested inf
    with pytest.raises(ValueError, match="(?i)finite|nan"):
        gate_track({"deep": {"deeper": {"x": float("nan")}}})                         # nested NaN


def _good_track():
    """A plausible bounded track payload (the shape track_record emits)."""
    return {
        "n_bets": 10, "beat_close_rate": 0.56, "avg_clv": 0.018,
        "rps": {"model": 0.10, "market": 0.12, "elo": 0.15},
        "reliability": [{"bin_lo": 0.0, "bin_hi": 0.1, "n": 3,
                         "forecast_mean": 0.05, "empirical": 0.0}],
        "is_synthetic": True,
    }


def test_gate_track_accepts_a_bounded_track():
    gate_track(_good_track())                                # no raise


def test_gate_track_rejects_out_of_range_beat_close_rate():
    """FIX E: a beat_close_rate of 1.4 is impossible (a rate is in [0,1]) — the 'too-good is a
    suspected bug' law made structural. RED before (only finiteness was checked, 1.4 is
    finite); GREEN after."""
    t = _good_track(); t["beat_close_rate"] = 1.4
    with pytest.raises(ValueError, match="(?i)beat_close_rate|range|\\[0"):
        gate_track(t)


def test_gate_track_rejects_negative_rps():
    """FIX E: a Ranked Probability Score is >= 0 by definition; a negative rps is a suspected
    bug and STOPS the build."""
    t = _good_track(); t["rps"]["model"] = -0.1
    with pytest.raises(ValueError, match="(?i)rps|negative|>= 0|non-negative"):
        gate_track(t)


def test_gate_track_rejects_negative_n_bets():
    t = _good_track(); t["n_bets"] = -1
    with pytest.raises(ValueError, match="(?i)n_bets|negative|>= 0|non-negative"):
        gate_track(t)


def test_gate_track_rejects_out_of_range_reliability_bin():
    """FIX E: a reliability bin's forecast_mean/empirical (when not None) is in [0,1]."""
    t = _good_track(); t["reliability"][0]["empirical"] = 1.4
    with pytest.raises(ValueError, match="(?i)reliability|empirical|forecast_mean|range|\\[0"):
        gate_track(t)
    t2 = _good_track(); t2["reliability"][0]["forecast_mean"] = -0.2
    with pytest.raises(ValueError, match="(?i)reliability|empirical|forecast_mean|range|\\[0"):
        gate_track(t2)


def test_gate_track_exempts_none_and_coverage_gap_metrics():
    """FIX E: None metrics + a coverage_gap track stay EXEMPT from the bounds (a gap/None is
    an honest absence, never a number to bound-check)."""
    gate_track(coverage_gap("no backtest records supplied"))         # the empty-records track
    t = _good_track(); t["rps"] = {"model": None, "market": None, "elo": None}
    t["beat_close_rate"] = None; t["avg_clv"] = None
    t["reliability"][0]["forecast_mean"] = None; t["reliability"][0]["empirical"] = None
    gate_track(t)                                                     # all-None metrics: no raise


def test_gate_fixture_forecast_rejects_non_finite_or_nonnumeric_grid_cells():
    base = {"most_likely": {"home_goals": 0, "away_goals": 0, "prob": 1.0},
            "one_x_two": {"home": 0.4, "draw": 0.3, "away": 0.3}}
    for bad_grid in ([[float("nan")]],            # NaN cell would slip the sum check
                     [[float("inf")]],            # inf cell
                     [[0.5, "x"]],                 # non-numeric cell (was TypeError)
                     [[0.5, None]]):               # None cell (was TypeError)
        with pytest.raises(ValueError, match="(?i)grid|finite|numeric"):
            gate_fixture_forecast({**base, "grid": bad_grid})
    # a valid numeric grid summing ~1 still passes
    gate_fixture_forecast({**base, "grid": [[0.5, 0.2], [0.2, 0.1]]})


def test_gate_fixture_forecast_rejects_empty_or_ragged_grid():
    base = {"most_likely": {"home_goals": 0, "away_goals": 0, "prob": 1.0},
            "one_x_two": {"home": 0.4, "draw": 0.3, "away": 0.3}}
    for bad in ([[], [1.0]],          # an empty row (was slipping; rest sums to 1)
                [[0.5], [0.5, 0.5]],  # ragged rows (unequal length)
                [[True, False]],      # bool cells masquerading as numbers
                []):                  # empty grid
        with pytest.raises(ValueError, match="(?i)grid"):
            gate_fixture_forecast({**base, "grid": bad})
    # a valid rectangular numeric grid summing ~1 still passes
    gate_fixture_forecast({**base, "grid": [[0.5, 0.2], [0.2, 0.1]]})


def test_gate_fixture_forecast_rejects_out_of_range_and_scalar_grid():
    base = {"most_likely": {"home_goals": 0, "away_goals": 0, "prob": 1.0},
            "one_x_two": {"home": 0.4, "draw": 0.3, "away": 0.3}}
    for bad in (1,                       # top-level scalar (was TypeError)
                "grid",                  # top-level string
                [[2.0, -1.0]],           # cells cancel to ~1 but are out of [0,1]
                [[-0.1, 1.1]],           # negative + >1 cells (sum ~1)
                [[0.5, 0.6]]):           # in-range but sums to 1.1 (bad-sum, still rejected)
        with pytest.raises(ValueError, match="(?i)grid|probab|sum"):
            gate_fixture_forecast({**base, "grid": bad})
    # a valid in-[0,1] rectangular grid summing ~1 still passes
    gate_fixture_forecast({**base, "grid": [[0.5, 0.2], [0.2, 0.1]]})


def test_gate_fixture_forecast_value_checks_headline_prob():
    """FIX C: ``most_likely.prob`` is value-checked (finite + in [0,1]), not merely
    key-present. Pre-fix the gate only checked ``"prob" in most_likely`` (and _write's
    sanitize_nans turns a NaN -> null BEFORE allow_nan=False, MASKING a NaN headline to
    null), so a NaN/out-of-range headline slipped. RED before (NaN/1.4 prob passes the
    presence check); GREEN after (value-checked -> raises)."""
    base = {"grid": [[0.5, 0.2], [0.2, 0.1]],
            "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}}
    for bad_prob in (float("nan"), float("inf"), 1.4, -0.1):
        with pytest.raises(ValueError, match="(?i)most_likely|prob|finite|range"):
            gate_fixture_forecast({**base,
                                   "most_likely": {"home_goals": 1, "away_goals": 0, "prob": bad_prob}})
    # a finite in-[0,1] headline prob still passes
    gate_fixture_forecast({**base, "most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12}})


def test_gate_fixture_forecast_value_checks_1x2_coherence():
    """FIX C: the 1X2 triple is value-checked — home/draw/away each finite in [0,1] AND
    summing to ~1 (a coherent all-three distribution). Pre-fix only key-PRESENCE was checked,
    so {0.5,0.5,0.5} (sums 1.5) or a >1 outcome slipped. RED before; GREEN after."""
    base = {"grid": [[0.5, 0.2], [0.2, 0.1]],
            "most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12}}
    # sums to 1.5 (not ~1)
    with pytest.raises(ValueError, match="(?i)1x2|sum|distribution"):
        gate_fixture_forecast({**base, "one_x_two": {"home": 0.5, "draw": 0.5, "away": 0.5}})
    # an out-of-range outcome (sum could still be ~1 with offsets, but the cell is >1)
    with pytest.raises(ValueError, match="(?i)1x2|range|finite|probab"):
        gate_fixture_forecast({**base, "one_x_two": {"home": 1.4, "draw": -0.3, "away": -0.1}})
    # a NaN outcome
    with pytest.raises(ValueError, match="(?i)1x2|finite|nan|probab"):
        gate_fixture_forecast({**base, "one_x_two": {"home": float("nan"), "draw": 0.2, "away": 0.1}})
    # a coherent triple summing ~1 still passes
    gate_fixture_forecast({**base, "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}})


def test_gate_fixture_forecast_value_checks_shortlist_probs():
    """FIX C: when the forecast carries a ``shortlist``, every entry's ``prob`` must be finite
    in [0,1] (no monotonicity requirement). Pre-fix the shortlist was never touched. RED
    before (a NaN/1.5 shortlist prob slips); GREEN after."""
    base = {"grid": [[0.5, 0.2], [0.2, 0.1]],
            "most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.5},
            "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}}
    for bad_prob in (float("nan"), 1.5, -0.2):
        with pytest.raises(ValueError, match="(?i)shortlist|prob|finite|range"):
            gate_fixture_forecast({**base, "shortlist": [
                {"home_goals": 1, "away_goals": 0, "prob": 0.5},
                {"home_goals": 0, "away_goals": 0, "prob": bad_prob}]})
    # a shortlist of finite in-[0,1] probs still passes
    gate_fixture_forecast({**base, "shortlist": [
        {"home_goals": 1, "away_goals": 0, "prob": 0.5},
        {"home_goals": 0, "away_goals": 0, "prob": 0.3}]})
