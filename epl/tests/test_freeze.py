"""Attacks on the three fixes and on the discipline that surrounds them.

Each test tries to make a fix fail rather than describing what it does. Where a
guard is asserted to hold, a POSITIVE CONTROL asserts it would have fired had
the thing it guards been broken — a leakage test that passes on a broken
implementation is worse than no test, because it is evidence that is not
evidence.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from epl import anchor as anchor_mod, baseline, dcfit, elo as elo_mod
from epl import freeze, windows
from epl.schema import sort_for_walk_forward


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    return baseline.load_matches()


@pytest.fixture(scope="module")
def frozen() -> dict:
    return freeze.load_frozen()


@pytest.fixture(scope="module")
def cfg(frozen) -> elo_mod.EloConfig:
    return elo_mod.EloConfig(**frozen["chosen"])


@pytest.fixture(scope="module")
def anchor(matches, cfg) -> anchor_mod.Anchor:
    return anchor_mod.Anchor(matches, cfg)


# --------------------------------------------------------------------------
# the discipline
# --------------------------------------------------------------------------
def test_windows_are_disjoint_and_exclude_the_partial_season():
    assert not set(windows.TUNE_SEASONS) & set(windows.SCORE_SEASONS)
    assert not set(windows.TUNE_SEASONS) & set(windows.EXCLUDED_SEASONS)
    assert not set(windows.SCORE_SEASONS) & set(windows.EXCLUDED_SEASONS)
    assert windows.EXCLUDED_SEASONS == ("2025/26",)


def test_the_objective_refuses_a_scoring_season(matches, cfg):
    """The guard sits where a number is actually assigned, not at the caller."""
    bad = sort_for_walk_forward(matches.loc[matches["season"].isin(
        list(windows.TUNE_SEASONS) + [windows.SCORE_SEASONS[0]])])
    with pytest.raises(ValueError, match="non-tuning season"):
        freeze._objective(bad, cfg)
    # POSITIVE CONTROL: the identical call on a legal frame returns a number,
    # so the test is detecting the season set and not some unrelated breakage.
    good = freeze._tuning_frame(matches)
    assert 0.0 < freeze._objective(good, cfg)["rps"] < 1.0


def test_frozen_file_was_tuned_only_on_the_tuning_window(frozen):
    assert frozen["tune_seasons"] == list(windows.TUNE_SEASONS)
    assert frozen["objective_seasons"] == list(windows.TUNE_SCORED)
    assert not set(frozen["objective_seasons"]) & set(windows.SCORE_SEASONS)
    # Every season the search actually walked, from its own audit trail.
    walked = {r["season"] for r in frozen["season_starts"]}
    assert walked == set(windows.TUNE_SEASONS)


def test_frozen_file_round_trips_into_a_config(frozen):
    cfg = elo_mod.EloConfig(**frozen["chosen"])
    assert cfg.k > 0 and cfg.promoted_offset <= 0
    assert frozen["chosen_tune_rps"] <= frozen["grid_median_rps"]


# --------------------------------------------------------------------------
# FIX 1 — the K factor
# --------------------------------------------------------------------------
def test_epl_still_falls_through_to_the_other_bucket():
    """The premise of Fix 1. If this changes, the fix silently re-scales K."""
    from wcmodel.data import tiers
    assert tiers.match_type(anchor_mod.TOURNAMENT_LABEL) == anchor_mod.MATCH_TYPE


def test_wcmodel_config_gives_an_epl_match_the_frozen_k(cfg):
    from wcmodel.config import load_config
    base = load_config()
    out = anchor_mod.wcmodel_config(base, cfg, "spec")
    got = out["elo"]["k_base"] * out["elo"]["k_by_match_type"][
        anchor_mod.MATCH_TYPE]
    assert got == pytest.approx(cfg.k)
    # The shipped config is what the probe is fixing; if they already agreed
    # there would be nothing to fix and this test should be deleted, not muted.
    shipped = base["elo"]["k_base"] * base["elo"]["k_by_match_type"][
        anchor_mod.MATCH_TYPE]
    assert shipped == pytest.approx(20.0)
    assert base["elo"]["k_base"] == 40.0
    # ...and the caller's config is never mutated.
    assert load_config()["elo"]["k_base"] == 40.0


def test_wcmodel_config_carries_an_anchor_token_into_the_cache_key(cfg):
    """Two anchors must not share a posterior cache key."""
    from wcmodel.config import load_config
    a = anchor_mod.wcmodel_config(load_config(), cfg, "anchor-A")
    b = anchor_mod.wcmodel_config(load_config(), cfg, "anchor-B")
    assert a["elo"] != b["elo"]
    assert json.dumps(a["elo"], sort_keys=True) != json.dumps(
        b["elo"], sort_keys=True)


def test_anchor_and_baseline_share_one_rating_table(matches, cfg, anchor):
    """The confound Fix 1 exists to remove, tested where it would show up.

    The rating the model anchors a club on at a cutoff must be the same number
    the Elo baseline prices that club's next match with. Checked on every match
    in the archive by `Anchor._verify_snapshots`; here on a sample, plus a
    positive control proving the check can fail.
    """
    from epl import walk
    hist = anchor.history
    keys = walk.cutoff_keys(
        sort_for_walk_forward(matches.loc[matches["played"]])).to_numpy()
    for i in (0, 500, 2000, len(hist) - 1):
        row = hist.iloc[i]
        state = anchor.state(keys[i], [row["home_key"], row["away_key"]])
        assert state.ratings[row["home_key"]] == row["elo_home_pre"]
        assert state.ratings[row["away_key"]] == row["elo_away_pre"]

    broken = anchor_mod.Anchor.__new__(anchor_mod.Anchor)
    broken.history = anchor.history
    broken._snapshots = [dict(s) for s in anchor._snapshots]
    broken._snapshots[3]["ratings"] = {
        k: v + 1.0 for k, v in broken._snapshots[3]["ratings"].items()}
    with pytest.raises(AssertionError, match="snapshot disagrees"):
        broken._verify_snapshots()


# --------------------------------------------------------------------------
# FIX 2 — the promoted-club prior
# --------------------------------------------------------------------------
def test_promoted_clubs_are_seeded_below_the_division_mean(matches, cfg):
    _, starts = elo_mod.compute_elo_history(matches, cfg)
    seeded = [s for s in starts if not s["first_season"]]
    assert seeded, "no season boundary in the archive?"
    for s in seeded:
        assert s["promoted_seed"] < s["division_mean"], s["season"]
        assert s["promoted_seed"] == pytest.approx(
            s["division_mean"] + cfg.promoted_offset)


def test_the_defect_is_reachable_and_was_beaten_on_data(frozen):
    """`promoted_offset = 0` — seeding AT the division mean — was in the grid."""
    levels = [m["value"] for m in frozen["marginals"]["promoted_offset"]]
    assert 0.0 in levels
    at_mean = next(m for m in frozen["marginals"]["promoted_offset"]
                   if m["value"] == 0.0)
    chosen = next(m for m in frozen["marginals"]["promoted_offset"]
                  if m["value"] == frozen["chosen"]["promoted_offset"])
    assert chosen["best_rps"] <= at_mean["best_rps"]


def test_promoted_seed_changes_a_promoted_clubs_anchor(matches, cfg):
    """A null fix would leave the ratings alone; this one must not."""
    a = anchor_mod.Anchor(matches, cfg)
    b = anchor_mod.Anchor(matches, cfg.replace(promoted_offset=0.0))
    opener = "2016-08-13"
    teams = ["burnley", "middlesbrough", "hull"]
    ra = a.state(opener, ["chelsea", "everton"]).ratings
    rb = b.state(opener, ["chelsea", "everton"]).ratings
    for t in teams:
        assert ra[t] < rb[t], t


def test_debut_offset_defaults_to_no_special_case(matches, cfg):
    """With `debut_offset = 0` a debutant is seeded exactly like any promotion."""
    zero = cfg.replace(debut_offset=0.0)
    _, starts = elo_mod.compute_elo_history(matches, zero)
    for s in starts:
        if not s["first_season"]:
            assert s["debut_seed"] == pytest.approx(s["promoted_seed"])
    # ...and the parameter is live: a non-zero value moves the debutant only.
    _, moved = elo_mod.compute_elo_history(
        matches, cfg.replace(debut_offset=-100.0))
    s16 = next(s for s in moved if s["season"] == "2015/16")
    assert set(s16["debuts"]) == {"bournemouth", "norwich", "watford"}
    assert s16["debut_seed"] == pytest.approx(s16["promoted_seed"] - 100.0)


# --------------------------------------------------------------------------
# FIX 3 — the cold start
# --------------------------------------------------------------------------
def test_cold_start_clubs_are_found_at_every_tuning_season_opener(matches):
    expected = {
        "2015/16": {"bournemouth", "norwich", "watford"},
        "2016/17": {"middlesbrough"},
        "2017/18": {"brighton", "huddersfield"},
        "2018/19": {"cardiff", "fulham", "wolves"},
    }
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    for season, want in expected.items():
        sub = played.loc[played["season"] == season]
        cutoff = pd.Timestamp(sub["date"].min())
        seen = set(played.loc[pd.to_datetime(played["date"]) < cutoff,
                              "home_key"]) | set(
            played.loc[pd.to_datetime(played["date"]) < cutoff, "away_key"])
        assert set(dcfit.cold_start_clubs(played, cutoff, sorted(seen))) == want


def test_a_cold_start_club_has_a_rating_but_no_history(matches, cfg, anchor):
    """The two facts that together make Fix 3 both necessary and possible."""
    opener = pd.Timestamp("2016-08-13")
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    before = played.loc[pd.to_datetime(played["date"]) < opener]
    seen = set(before["home_key"]) | set(before["away_key"])
    assert "middlesbrough" not in seen           # no history -> no team index
    state = anchor.state(opener, sorted(seen))
    assert "middlesbrough" in state.ratings      # but it does have a rating
    assert state.z("middlesbrough") < 0          # ...and it is below the mean


def _fake_posterior(teams, n_draws=40, seed=0):
    """A Posterior over a toy idata — enough for the predict path, no ADVI."""
    rng = np.random.default_rng(seed)
    n = len(teams)
    ds = xr.Dataset({
        "att": (("chain", "draw", "team"), rng.normal(0, .3, (1, n_draws, n))),
        "def": (("chain", "draw", "team"), rng.normal(0, .3, (1, n_draws, n))),
        "mu": (("chain", "draw"), rng.normal(0.1, .05, (1, n_draws))),
        "home_adv": (("chain", "draw"), rng.normal(0.25, .05, (1, n_draws))),
        "rho": (("chain", "draw"), rng.normal(0.0, .02, (1, n_draws))),
        "sigma_att": (("chain", "draw"), np.abs(rng.normal(.4, .05, (1, n_draws)))),
        "sigma_def": (("chain", "draw"), np.abs(rng.normal(.4, .05, (1, n_draws)))),
    })
    # `att` must be centred, as the model's soft sum-to-zero makes it.
    for name in ("att", "def"):
        ds[name] = ds[name] - ds[name].mean("team")

    class _IData:
        posterior = ds

    from wcmodel.model.posterior import Posterior
    return Posterior(_IData(), teams, "dixon_coles")


def _state(ratings, teams):
    r = np.array([ratings[t] for t in teams], float)
    return anchor_mod.AnchorState(cutoff=pd.Timestamp("2016-08-13"),
                                  ratings=dict(ratings), teams=tuple(teams),
                                  mean=float(r.mean()), sd=float(r.std()))


def test_cold_start_makes_every_fixture_priceable():
    from wcmodel.config import load_config
    teams = [f"club_{i}" for i in range(19)]
    base = _fake_posterior(teams)
    ratings = {t: 1500.0 + 40 * i for i, t in enumerate(teams)}
    ratings["newcomer"] = 1400.0
    state = _state(ratings, teams)

    with pytest.raises(KeyError):
        base.predict_1x2("newcomer", "club_0")          # the defect

    cfg = load_config()
    extra = {"newcomer": dcfit._prior_draws(state, "newcomer", cfg, base, 7)}
    post = dcfit.ColdStartPosterior(base, extra)
    p = post.predict_1x2("newcomer", "club_0")
    assert set(p) == {"home", "draw", "away"}
    assert sum(p.values()) == pytest.approx(1.0, abs=1e-9)
    assert all(0.0 < v < 1.0 for v in p.values())
    assert "newcomer" in post.provisional_teams        # widened, as it should be


def test_cold_start_leaves_every_fitted_club_bit_identical():
    from wcmodel.config import load_config
    teams = [f"club_{i}" for i in range(19)]
    base = _fake_posterior(teams)
    ratings = {t: 1500.0 + 40 * i for i, t in enumerate(teams)}
    ratings["newcomer"] = 1400.0
    extra = {"newcomer": dcfit._prior_draws(
        _state(ratings, teams), "newcomer", load_config(), base, 7)}
    post = dcfit.ColdStartPosterior(base, extra)
    for h, a in (("club_1", "club_2"), ("club_18", "club_0")):
        assert post.predict_1x2(h, a) == base.predict_1x2(h, a)


def test_cold_start_is_deterministic_and_reads_the_anchor():
    """Same club, same seed -> same forecast; lower seed -> weaker forecast."""
    from wcmodel.config import load_config
    cfg = load_config()
    teams = [f"club_{i}" for i in range(19)]
    base = _fake_posterior(teams)
    ratings = {t: 1500.0 + 40 * i for i, t in enumerate(teams)}

    def price(seed_rating):
        r = dict(ratings, newcomer=seed_rating)
        extra = {"newcomer": dcfit._prior_draws(
            _state(r, teams), "newcomer", cfg, base, 7)}
        return dcfit.ColdStartPosterior(base, extra).predict_1x2(
            "newcomer", "club_9")

    assert price(1400.0) == price(1400.0)                       # deterministic
    weak, strong = price(1300.0), price(1900.0)
    assert weak["home"] < strong["home"]                        # anchor is live
    assert weak["away"] > strong["away"]


def test_cold_start_prior_matches_the_models_own_prior():
    """The draws ARE `Normal(k * z, sigma)` — the model's prior, not a new one."""
    from wcmodel.config import load_config
    cfg = load_config()
    strength = cfg["model"]["strength_prior"]
    if not strength["enabled"]:
        pytest.skip("strength prior disabled in the shipped config")
    teams = [f"club_{i}" for i in range(19)]
    base = _fake_posterior(teams, n_draws=20000, seed=3)
    ratings = {t: 1500.0 + 40 * i for i, t in enumerate(teams)}
    ratings["newcomer"] = 1400.0
    state = _state(ratings, teams)
    draws = dcfit._prior_draws(state, "newcomer", cfg, base, 11)
    z = state.z("newcomer")
    sigma = np.asarray(base._post("sigma_att"), float).ravel()
    assert draws["att"].mean() == pytest.approx(
        strength["k_att"] * z, abs=4 * sigma.mean() / np.sqrt(sigma.size))
    assert draws["att"].std() == pytest.approx(sigma.mean(), rel=0.1)


# --------------------------------------------------------------------------
# point-in-time — the property everything else rests on
# --------------------------------------------------------------------------
def test_rewriting_the_future_does_not_move_the_anchor(matches, cfg):
    """Canary: every post-cutoff result becomes 9-0, every earlier anchor holds."""
    cutoff = pd.Timestamp("2017-01-01")
    played = sort_for_walk_forward(matches.loc[matches["played"]]).copy()
    real = anchor_mod.Anchor(played, cfg)

    tampered = played.copy()
    after = pd.to_datetime(tampered["date"]) >= cutoff
    tampered.loc[after, ["fthg", "ftag"]] = [9, 0]
    tampered.loc[after, "ftr"] = "H"
    fake = anchor_mod.Anchor(tampered, cfg)

    teams = sorted(set(played.loc[~after, "home_key"]))
    a = real.state(cutoff, teams).ratings
    b = fake.state(cutoff, teams).ratings
    for t in teams:
        assert a[t] == b[t], t
    # POSITIVE CONTROL: the tampering must actually have moved something later.
    later = pd.Timestamp("2017-05-01")
    la = real.state(later, teams).ratings
    lb = fake.state(later, teams).ratings
    assert any(la[t] != lb[t] for t in teams)


def test_anchor_z_is_standardised_over_the_fitted_teams(matches, cfg, anchor):
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    cutoff = pd.Timestamp("2018-01-06")
    before = played.loc[pd.to_datetime(played["date"]) < cutoff]
    teams = sorted(set(before["home_key"]) | set(before["away_key"]))
    z = anchor.state(cutoff, teams).elo_z(teams)
    assert z.shape == (len(teams),)
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert z.std() == pytest.approx(1.0, abs=1e-12)
